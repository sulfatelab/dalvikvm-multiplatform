#include <jni.h>
#include <windows.h>

#include <stdint.h>

static JavaVM* g_vm;

typedef struct WorkerArgs {
  jclass probe_class;
  jmethodID callback;
  int daemon;
  int iteration;
  int status;
} WorkerArgs;

static DWORD WINAPI RunAttachedThread(LPVOID opaque) {
  WorkerArgs* args = (WorkerArgs*)opaque;
  JNIEnv* env = NULL;
  JavaVMAttachArgs attach_args;
  attach_args.version = JNI_VERSION_1_6;
  attach_args.name = args->daemon ? "W002AttachDaemon" : "W002AttachRegular";
  attach_args.group = NULL;

  jint rc;
  if (args->daemon) {
    rc = (*g_vm)->AttachCurrentThreadAsDaemon(g_vm, &env, &attach_args);
  } else {
    rc = (*g_vm)->AttachCurrentThread(g_vm, &env, &attach_args);
  }
  if (rc != JNI_OK || env == NULL) {
    args->status = 10 + rc;
    return 0;
  }

  const jlong expected = INT64_C(0x1234567800000000) +
      (args->daemon ? INT64_C(0x01000000) : 0) + args->iteration;
  const jlong actual = (*env)->CallStaticLongMethod(
      env, args->probe_class, args->callback, args->daemon ? JNI_TRUE : JNI_FALSE, args->iteration);
  if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env);
    (*env)->ExceptionClear(env);
    args->status = 20;
  } else if (actual != expected) {
    args->status = 21;
  }

  if ((*g_vm)->DetachCurrentThread(g_vm) != JNI_OK && args->status == 0) {
    args->status = 30;
  }
  env = NULL;
  if ((*g_vm)->GetEnv(g_vm, (void**)&env, JNI_VERSION_1_6) != JNI_EDETACHED &&
      args->status == 0) {
    args->status = 31;
  }
  return 0;
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
  (void)reserved;
  g_vm = vm;
  return JNI_VERSION_1_6;
}

JNIEXPORT jint JNICALL Java_W002AttachProbe_runAttachMatrix(
    JNIEnv* env, jclass probe_class, jint iterations) {
  if (g_vm == NULL || iterations <= 0) {
    return -1;
  }

  jclass global_class = (jclass)(*env)->NewGlobalRef(env, probe_class);
  if (global_class == NULL) {
    return -2;
  }
  jmethodID callback = (*env)->GetStaticMethodID(env, probe_class, "attachedCallback", "(ZI)J");
  if (callback == NULL) {
    (*env)->DeleteGlobalRef(env, global_class);
    return -3;
  }

  int completed = 0;
  for (int daemon = 0; daemon <= 1; ++daemon) {
    for (int iteration = 0; iteration < iterations; ++iteration) {
      WorkerArgs args;
      args.probe_class = global_class;
      args.callback = callback;
      args.daemon = daemon;
      args.iteration = iteration;
      args.status = 0;

      HANDLE thread = CreateThread(NULL, 0, RunAttachedThread, &args, 0, NULL);
      if (thread == NULL) {
        completed = -100;
        goto done;
      }
      DWORD wait_result = WaitForSingleObject(thread, 30000);
      CloseHandle(thread);
      if (wait_result != WAIT_OBJECT_0) {
        completed = -101;
        goto done;
      }
      if (args.status != 0) {
        completed = -args.status;
        goto done;
      }
      ++completed;
    }
  }

done:
  (*env)->DeleteGlobalRef(env, global_class);
  return completed;
}
