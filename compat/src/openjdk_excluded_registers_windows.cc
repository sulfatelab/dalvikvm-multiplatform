#include <jni.h>

// Windows does not expose the Linux NIO.2 filesystem providers selected out
// of libopenjdk. Keep OnLoad's registration surface complete and explicit.
extern "C" void register_java_sun_nio_fs_UnixNativeDispatcher(JNIEnv*) {}
extern "C" void register_java_util_prefs_FileSystemPreferences(JNIEnv*) {}
extern "C" void register_java_io_UnixFileSystem(JNIEnv*) {}
