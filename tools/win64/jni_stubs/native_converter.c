/* OBSOLETE / NON-PRODUCT (W-006 CLOSED).
 * Phase-2 minimal NativeConverter stub. Product uses real AOSP ICU:
 *   vendor/icu/android_icu4j/.../com_android_icu_charset_NativeConverter.cpp
 * in icu_jni.dll via tools/win64/stage_native_modules.sh.
 * Kept only for historical reference; not linked into product PE.
 */
/* Minimal com.android.icu.charset.NativeConverter PE stub for Phase-2.
 * Supports UTF-8 / ISO-8859-1 / US-ASCII / UTF-16* enough for System/print/zip bootstrap.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <jni.h>

enum {
  U_ZERO_ERROR = 0,
  U_ILLEGAL_ARGUMENT_ERROR = 1,
  U_BUFFER_OVERFLOW_ERROR = 15,
  U_INVALID_CHAR_FOUND = 10,
  U_ILLEGAL_CHAR_FOUND = 12,
  U_TRUNCATED_CHAR_FOUND = 11,
};

typedef struct {
  int kind; /* 0=utf8, 1=latin1, 2=ascii, 3=utf16le, 4=utf16be, 5=utf16 */
} Conv;

static int streq_ci(const char* a, const char* b) {
  if (!a || !b) return 0;
  while (*a && *b) {
    char ca = *a, cb = *b;
    if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');
    if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');
    if (ca != cb) return 0;
    ++a; ++b;
  }
  return *a == 0 && *b == 0;
}

static int kind_for_name(const char* name) {
  if (streq_ci(name, "UTF-8") || streq_ci(name, "UTF8") || streq_ci(name, "unicode-1-1-utf-8")) return 0;
  if (streq_ci(name, "ISO-8859-1") || streq_ci(name, "ISO8859_1") || streq_ci(name, "latin1") || streq_ci(name, "ISO_8859_1")) return 1;
  if (streq_ci(name, "US-ASCII") || streq_ci(name, "ASCII") || streq_ci(name, "ANSI_X3.4-1968")) return 2;
  if (streq_ci(name, "UTF-16LE") || streq_ci(name, "UnicodeLittleUnmarked")) return 3;
  if (streq_ci(name, "UTF-16BE") || streq_ci(name, "UnicodeBigUnmarked")) return 4;
  if (streq_ci(name, "UTF-16") || streq_ci(name, "Unicode") || streq_ci(name, "UTF_16")) return 5;
  return -1;
}

static const char* java_name_for_kind(int k) {
  switch (k) {
    case 0: return "UTF-8";
    case 1: return "ISO-8859-1";
    case 2: return "US-ASCII";
    case 3: return "UTF-16LE";
    case 4: return "UTF-16BE";
    case 5: return "UTF-16";
    default: return NULL;
  }
}

static void FreeNativeConverter(void* p) { free(p); }

/* ===== open/close/meta ===== */
__declspec(dllexport) jlong Java_com_android_icu_charset_NativeConverter_openConverter(JNIEnv* env, jclass cls, jstring name) {
  (void)cls;
  if (!name) return 0;
  const char* c = (*env)->GetStringUTFChars(env, name, 0);
  if (!c) return 0;
  int k = kind_for_name(c);
  (*env)->ReleaseStringUTFChars(env, name, c);
  if (k < 0) return 0;
  Conv* conv = (Conv*)malloc(sizeof(Conv));
  if (!conv) return 0;
  conv->kind = k;
  return (jlong)(intptr_t)conv;
}
__declspec(dllexport) void Java_com_android_icu_charset_NativeConverter_closeConverter(JNIEnv* env, jclass cls, jlong addr) {
  (void)env; (void)cls; free((void*)(intptr_t)addr);
}
__declspec(dllexport) void Java_com_android_icu_charset_NativeConverter_resetByteToChar(JNIEnv* env, jclass cls, jlong addr) { (void)env;(void)cls;(void)addr; }
__declspec(dllexport) void Java_com_android_icu_charset_NativeConverter_resetCharToByte(JNIEnv* env, jclass cls, jlong addr) { (void)env;(void)cls;(void)addr; }
__declspec(dllexport) jint Java_com_android_icu_charset_NativeConverter_getMaxBytesPerChar(JNIEnv* env, jclass cls, jlong addr) {
  (void)env;(void)cls; Conv* c=(Conv*)(intptr_t)addr; if(!c) return 1;
  return (c->kind==3||c->kind==4||c->kind==5)?2: (c->kind==0?3:1);
}
__declspec(dllexport) jfloat Java_com_android_icu_charset_NativeConverter_getAveBytesPerChar(JNIEnv* env, jclass cls, jlong addr) {
  return (jfloat)Java_com_android_icu_charset_NativeConverter_getMaxBytesPerChar(env,cls,addr);
}
__declspec(dllexport) jfloat Java_com_android_icu_charset_NativeConverter_getAveCharsPerByte(JNIEnv* env, jclass cls, jlong addr) {
  jint m = Java_com_android_icu_charset_NativeConverter_getMaxBytesPerChar(env,cls,addr);
  return m ? (1.0f / (jfloat)m) : 1.0f;
}
__declspec(dllexport) jbyteArray Java_com_android_icu_charset_NativeConverter_getSubstitutionBytes(JNIEnv* env, jclass cls, jlong addr) {
  (void)cls;(void)addr;
  jbyteArray a = (*env)->NewByteArray(env, 1);
  jbyte b = (jbyte)'?';
  (*env)->SetByteArrayRegion(env, a, 0, 1, &b);
  return a;
}
__declspec(dllexport) jboolean Java_com_android_icu_charset_NativeConverter_contains(JNIEnv* env, jclass cls, jstring a, jstring b) {
  (void)env;(void)cls;(void)a;(void)b; return JNI_TRUE;
}
__declspec(dllexport) void Java_com_android_icu_charset_NativeConverter_setCallbackDecode(JNIEnv* env, jclass cls, jlong h, jint a, jint b, jstring s) {
  (void)env;(void)cls;(void)h;(void)a;(void)b;(void)s;
}
__declspec(dllexport) void Java_com_android_icu_charset_NativeConverter_setCallbackEncode(JNIEnv* env, jclass cls, jlong h, jint a, jint b, jbyteArray s) {
  (void)env;(void)cls;(void)h;(void)a;(void)b;(void)s;
}
__declspec(dllexport) jlong Java_com_android_icu_charset_NativeConverter_getNativeFinalizer(JNIEnv* env, jclass cls) {
  (void)env;(void)cls; return (jlong)(intptr_t)&FreeNativeConverter;
}

__declspec(dllexport) jobjectArray Java_com_android_icu_charset_NativeConverter_getAvailableCharsetNames(JNIEnv* env, jclass cls) {
  (void)cls;
  static const char* names[] = {"UTF-8","ISO-8859-1","US-ASCII","UTF-16","UTF-16LE","UTF-16BE"};
  jclass sc = (*env)->FindClass(env, "java/lang/String");
  jobjectArray arr = (*env)->NewObjectArray(env, 6, sc, 0);
  for (int i=0;i<6;i++) (*env)->SetObjectArrayElement(env, arr, i, (*env)->NewStringUTF(env, names[i]));
  return arr;
}

/* charsetForName -> new CharsetICU(javaName, icuName, aliases) */
__declspec(dllexport) jobject Java_com_android_icu_charset_NativeConverter_charsetForName(JNIEnv* env, jclass cls, jstring charsetName) {
  (void)cls;
  if (!charsetName) return NULL;
  if ((*env)->PushLocalFrame(env, 16) < 0) return NULL;
  const char* c = (*env)->GetStringUTFChars(env, charsetName, 0);
  if (!c) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  int k = kind_for_name(c);
  (*env)->ReleaseStringUTFChars(env, charsetName, c);
  if (k < 0) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  const char* jn = java_name_for_kind(k);
  jclass csi = (*env)->FindClass(env, "com/android/icu/charset/CharsetICU");
  if (!csi) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jmethodID ctor = (*env)->GetMethodID(env, csi, "<init>", "(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)V");
  if (!ctor) { (*env)->PopLocalFrame(env, NULL); return NULL; }
  jclass sc = (*env)->FindClass(env, "java/lang/String");
  jobjectArray aliases = (*env)->NewObjectArray(env, 1, sc, 0);
  (*env)->SetObjectArrayElement(env, aliases, 0, (*env)->NewStringUTF(env, jn));
  jstring javaName = (*env)->NewStringUTF(env, jn);
  jstring icuName = (*env)->NewStringUTF(env, jn);
  jobject obj = (*env)->NewObject(env, csi, ctor, javaName, icuName, aliases);
  return (*env)->PopLocalFrame(env, obj);
}

/* ===== encode (chars -> bytes) =====
 * data[0]: in=start, out=chars consumed this call
 * data[1]: in=start, out=absolute output end index (array offset + pos after write)
 */
__declspec(dllexport) jint Java_com_android_icu_charset_NativeConverter_encode(
    JNIEnv* env, jclass cls, jlong address,
    jcharArray source, jint sourceEnd, jbyteArray target, jint targetEnd,
    jintArray data, jboolean flush) {
  (void)cls; (void)flush;
  Conv* conv = (Conv*)(intptr_t)address;
  if (!conv || !source || !target || !data) return U_ILLEGAL_ARGUMENT_ERROR;
  jint d[3];
  (*env)->GetIntArrayRegion(env, data, 0, 3, d);
  jint srcOff = d[0], tgtOff = d[1];
  jsize srcLen = sourceEnd - srcOff;
  jsize tgtCap = targetEnd - tgtOff;
  if (srcLen < 0 || tgtCap < 0) return U_ILLEGAL_ARGUMENT_ERROR;
  jchar* src = (jchar*)malloc((size_t)srcLen * sizeof(jchar));
  jbyte* tgt = (jbyte*)malloc((size_t)tgtCap);
  if (!src || !tgt) { free(src); free(tgt); return U_ILLEGAL_ARGUMENT_ERROR; }
  (*env)->GetCharArrayRegion(env, source, srcOff, srcLen, src);

  jint si=0, ti=0;
  jint err = U_ZERO_ERROR;
  while (si < srcLen) {
    jchar ch = src[si];
    if (conv->kind == 0) { /* UTF-8 */
      if (ch < 0x80) {
        if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jbyte)ch; si++;
      } else if (ch < 0x800) {
        if (ti + 1 >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jbyte)(0xC0 | (ch >> 6));
        tgt[ti++] = (jbyte)(0x80 | (ch & 0x3F)); si++;
      } else if (ch >= 0xD800 && ch <= 0xDBFF) {
        if (si + 1 >= srcLen) { err = U_TRUNCATED_CHAR_FOUND; d[2]=1; break; }
        jchar ch2 = src[si+1];
        if (ch2 < 0xDC00 || ch2 > 0xDFFF) { err = U_ILLEGAL_CHAR_FOUND; d[2]=1; break; }
        uint32_t cp = 0x10000 + (((ch - 0xD800) << 10) | (ch2 - 0xDC00));
        if (ti + 3 >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jbyte)(0xF0 | (cp >> 18));
        tgt[ti++] = (jbyte)(0x80 | ((cp >> 12) & 0x3F));
        tgt[ti++] = (jbyte)(0x80 | ((cp >> 6) & 0x3F));
        tgt[ti++] = (jbyte)(0x80 | (cp & 0x3F));
        si += 2;
      } else {
        if (ti + 2 >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jbyte)(0xE0 | (ch >> 12));
        tgt[ti++] = (jbyte)(0x80 | ((ch >> 6) & 0x3F));
        tgt[ti++] = (jbyte)(0x80 | (ch & 0x3F)); si++;
      }
    } else if (conv->kind == 1) { /* latin1 */
      if (ch > 0xFF) { err = U_INVALID_CHAR_FOUND; d[2]=1; break; }
      if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
      tgt[ti++] = (jbyte)ch; si++;
    } else if (conv->kind == 2) { /* ascii */
      if (ch > 0x7F) { err = U_INVALID_CHAR_FOUND; d[2]=1; break; }
      if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
      tgt[ti++] = (jbyte)ch; si++;
    } else { /* utf16 family: write LE/BE */
      if (ti + 1 >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
      if (conv->kind == 4) { /* BE */
        tgt[ti++] = (jbyte)(ch >> 8); tgt[ti++] = (jbyte)(ch & 0xFF);
      } else { /* LE and UTF-16 default LE for phase2 */
        tgt[ti++] = (jbyte)(ch & 0xFF); tgt[ti++] = (jbyte)(ch >> 8);
      }
      si++;
    }
  }

  if (ti > 0) (*env)->SetByteArrayRegion(env, target, tgtOff, ti, tgt);
  d[0] = si;              /* chars consumed */
  d[1] = tgtOff + ti;     /* absolute end index for encoder setPosition */
  (*env)->SetIntArrayRegion(env, data, 0, 3, d);
  free(src); free(tgt);
  return err;
}

/* ===== decode (bytes -> chars) =====
 * data[0]/data[1]: in start, out amount consumed/written this call
 */
__declspec(dllexport) jint Java_com_android_icu_charset_NativeConverter_decode(
    JNIEnv* env, jclass cls, jlong address,
    jbyteArray source, jint sourceEnd, jcharArray target, jint targetEnd,
    jintArray data, jboolean flush) {
  (void)cls; (void)flush;
  Conv* conv = (Conv*)(intptr_t)address;
  if (!conv || !source || !target || !data) return U_ILLEGAL_ARGUMENT_ERROR;
  jint d[3] = {0,0,0};
  (*env)->GetIntArrayRegion(env, data, 0, 3, d);
  jint srcOff = d[0], tgtOff = d[1];
  jsize srcLen = sourceEnd - srcOff;
  jsize tgtCap = targetEnd - tgtOff;
  if (srcLen < 0 || tgtCap < 0) return U_ILLEGAL_ARGUMENT_ERROR;
  jbyte* src = (jbyte*)malloc((size_t)srcLen);
  jchar* tgt = (jchar*)malloc((size_t)tgtCap * sizeof(jchar));
  if (!src || !tgt) { free(src); free(tgt); return U_ILLEGAL_ARGUMENT_ERROR; }
  (*env)->GetByteArrayRegion(env, source, srcOff, srcLen, src);

  jint si=0, ti=0, err=U_ZERO_ERROR;
  while (si < srcLen) {
    unsigned char b = (unsigned char)src[si];
    if (conv->kind == 0) {
      if (b < 0x80) {
        if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jchar)b; si++;
      } else if ((b & 0xE0) == 0xC0) {
        if (si + 1 >= srcLen) { err = U_TRUNCATED_CHAR_FOUND; d[2]=srcLen-si; break; }
        unsigned char b2 = (unsigned char)src[si+1];
        if ((b2 & 0xC0) != 0x80) { err = U_ILLEGAL_CHAR_FOUND; d[2]=1; break; }
        if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jchar)(((b & 0x1F) << 6) | (b2 & 0x3F)); si += 2;
      } else if ((b & 0xF0) == 0xE0) {
        if (si + 2 >= srcLen) { err = U_TRUNCATED_CHAR_FOUND; d[2]=srcLen-si; break; }
        unsigned char b2=(unsigned char)src[si+1], b3=(unsigned char)src[si+2];
        if ((b2&0xC0)!=0x80 || (b3&0xC0)!=0x80) { err=U_ILLEGAL_CHAR_FOUND; d[2]=1; break; }
        if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        tgt[ti++] = (jchar)(((b&0x0F)<<12)|((b2&0x3F)<<6)|(b3&0x3F)); si += 3;
      } else if ((b & 0xF8) == 0xF0) {
        if (si + 3 >= srcLen) { err = U_TRUNCATED_CHAR_FOUND; d[2]=srcLen-si; break; }
        unsigned char b2=(unsigned char)src[si+1], b3=(unsigned char)src[si+2], b4=(unsigned char)src[si+3];
        if ((b2&0xC0)!=0x80||(b3&0xC0)!=0x80||(b4&0xC0)!=0x80){err=U_ILLEGAL_CHAR_FOUND;d[2]=1;break;}
        if (ti + 1 >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
        uint32_t cp = ((b&0x07)<<18)|((b2&0x3F)<<12)|((b3&0x3F)<<6)|(b4&0x3F);
        cp -= 0x10000;
        tgt[ti++] = (jchar)(0xD800 + (cp >> 10));
        tgt[ti++] = (jchar)(0xDC00 + (cp & 0x3FF));
        si += 4;
      } else { err = U_ILLEGAL_CHAR_FOUND; d[2]=1; break; }
    } else if (conv->kind == 1 || conv->kind == 2) {
      if (conv->kind==2 && b>0x7F) { err=U_INVALID_CHAR_FOUND; d[2]=1; break; }
      if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
      tgt[ti++] = (jchar)b; si++;
    } else {
      if (si + 1 >= srcLen) { err = U_TRUNCATED_CHAR_FOUND; d[2]=srcLen-si; break; }
      if (ti >= tgtCap) { err = U_BUFFER_OVERFLOW_ERROR; break; }
      unsigned char b2 = (unsigned char)src[si+1];
      jchar ch = (conv->kind==4) ? (jchar)((b<<8)|b2) : (jchar)((b2<<8)|b);
      tgt[ti++] = ch; si += 2;
    }
  }
  if (ti > 0) (*env)->SetCharArrayRegion(env, target, tgtOff, ti, tgt);
  d[0] = si;
  d[1] = ti;
  (*env)->SetIntArrayRegion(env, data, 0, 3, d);
  free(src); free(tgt);
  return err;
}

/* registerConverter(Object referrent, long converterHandle) - no-op for Phase-2 stub. */
__declspec(dllexport) void Java_com_android_icu_charset_NativeConverter_registerConverter(
    JNIEnv* env, jclass cls, jobject referrent, jlong address) {
  (void)env; (void)cls; (void)referrent; (void)address;
}
