# Win64 PE: real ICU4C + libicu_jni + (staged) libcore natives.
# Replaces tools/win64/jni_stubs/libcombined.dll for modules we successfully build.
#
# Configure:
#   source $WIN64_DEV_ENV/env.sh
#   cmake -S tools/verify/win64_libcore_icu -B build/win64_libcore_icu -G Ninja \
#     -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN -DCMAKE_BUILD_TYPE=RelWithDebInfo
#   cmake --build build/win64_libcore_icu -j$(nproc)
#
# Phase A (default): icuuc_stubdata, icuuc, icui18n, icu_jni
# Phase B: enable -DMDVM_WIN64_BUILD_JAVACORE=ON etc. as ports land.

cmake_minimum_required(VERSION 3.20)
project(Win64LibcoreIcu CXX C)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "Need LLVM clang for Win64 PE (got ${CMAKE_CXX_COMPILER_ID})")
endif()
if(MSVC)
  message(FATAL_ERROR "MSVC cl/clang-cl not supported")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(MDVM_NATIVE_SRC_ROOT_DIR "${_repo}/vendor" CACHE PATH "")
set(MDVM_ART_ROOT_DIR "${_repo}/vendor" CACHE PATH "")
set(MDVM_ICU_DIR "${_repo}/vendor/icu" CACHE PATH "")
set(MDVM_LIBCORE_DIR "${_repo}/vendor/libcore" CACHE PATH "")
set(MDVM_FDLIBM_DIR "${_repo}/vendor/java-external/fdlibm" CACHE PATH "")
set(MDVM_COMPAT_INCLUDE_DIR "${_repo}/compat/include" CACHE PATH "")
set(MDVM_WIN64_ENV "$ENV{WIN64_DEV_ENV}" CACHE PATH "")
if(NOT MDVM_WIN64_ENV)
  set(MDVM_WIN64_ENV "/home/agent/Projects/win64-dev-env" CACHE PATH "" FORCE)
endif()

option(MDVM_WIN64_BUILD_JAVACORE "Build hybrid real libjavacore PE" ON)
option(MDVM_WIN64_BUILD_OPENJDK "Build real libopenjdk PE (Unix/NIO hybrid)" ON)

include(${CMAKE_CURRENT_SOURCE_DIR}/sources.cmake)

# zlib (prebuilt in win64-dev-env)
set(_ZLIB_ROOT "${MDVM_WIN64_ENV}/lib/zlib")
add_library(z STATIC IMPORTED GLOBAL)
set_target_properties(z PROPERTIES
  IMPORTED_LOCATION "${_ZLIB_ROOT}/lib/z.lib"
  INTERFACE_INCLUDE_DIRECTORIES "${_ZLIB_ROOT}/include")

# --- already-built phase1 deps we link against (import from build/win64_phase1) ---
set(MDVM_WIN64_PHASE1_DIR "${_repo}/build/win64_phase1" CACHE PATH "phase1 PE build dir")

function(mdvm_import_dll name)
  add_library(${name} SHARED IMPORTED GLOBAL)
  set_target_properties(${name} PROPERTIES
    IMPORTED_LOCATION "${MDVM_WIN64_PHASE1_DIR}/${name}.dll"
    IMPORTED_IMPLIB "${MDVM_WIN64_PHASE1_DIR}/${name}.lib")
endfunction()

foreach(_d base log nativehelper ziparchive)
  if(EXISTS "${MDVM_WIN64_PHASE1_DIR}/${_d}.dll")
    mdvm_import_dll(${_d})
  else()
    message(WARNING "Missing phase1 import ${_d}.dll — link may fail")
  endif()
endforeach()

set(_WIN_INCLUDES
  "${MDVM_COMPAT_INCLUDE_DIR}"
  "${MDVM_ART_ROOT_DIR}/libnativehelper/include_jni"
  "${MDVM_ART_ROOT_DIR}/libnativehelper/header_only_include"
  "${MDVM_ART_ROOT_DIR}/libnativehelper/include"
  "${MDVM_ART_ROOT_DIR}/libnativehelper/include_platform"
  "${MDVM_ART_ROOT_DIR}/libnativehelper/include_platform_header_only"
  "${MDVM_ART_ROOT_DIR}/libbase/include"
  "${MDVM_ART_ROOT_DIR}/external/fmtlib/include"
  "${MDVM_ART_ROOT_DIR}/logging/liblog/include"
)

set(_ICU_COMMON_INCLUDES
  "${MDVM_ICU_DIR}/icu4c/source/common"
  "${MDVM_ICU_DIR}/android_icu4c/include"
  "${MDVM_ICU_DIR}/icu4c/source/i18n"
)

set(_WIN_DEFS _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN)
set(_WIN_CFLAGS -Wno-unused-parameter -Wno-deprecated-declarations -Wno-sign-compare -Wno-missing-field-initializers)
set(_WIN_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_win64_prelude.h")


# --- icuuc (stubdata sources compiled into this DLL) ---
# Windows treats U_ICUDATA_ENTRY_POINT as dllimport unless U_COMMON_IMPLEMENTATION is set
# while compiling both udata.cpp and stubdata.cpp into the same image.
add_library(icuuc SHARED ${ICUUC_SRCS} ${ICUUC_STUBDATA_SRCS})
target_include_directories(icuuc PUBLIC ${_ICU_COMMON_INCLUDES})
target_compile_definitions(icuuc PRIVATE ${_WIN_DEFS} U_COMMON_IMPLEMENTATION PIC _REENTRANT)
target_compile_options(icuuc PRIVATE ${_WIN_CFLAGS} -frtti)
target_compile_definitions(icuuc PUBLIC U_PLATFORM=U_PF_WINDOWS)


# --- icui18n ---
add_library(icui18n SHARED ${ICUI18N_SRCS})
target_include_directories(icui18n PUBLIC ${_ICU_COMMON_INCLUDES})
target_compile_definitions(icui18n PRIVATE ${_WIN_DEFS} U_I18N_IMPLEMENTATION PIC _REENTRANT)
target_compile_options(icui18n PRIVATE ${_WIN_CFLAGS} -frtti -Wno-unreachable-code-loop-increment)
target_link_libraries(icui18n PUBLIC icuuc)

# --- icu_jni (real NativeConverter etc.) ---
add_library(icu_jni SHARED ${ICU_JNI_SRCS})
set_target_properties(icu_jni PROPERTIES OUTPUT_NAME "libicu_jni")

target_include_directories(icu_jni PUBLIC
  ${_WIN_INCLUDES}
  ${_ICU_COMMON_INCLUDES}
  "${MDVM_ICU_DIR}/android_icu4j/libcore_bridge/src/native"
)
target_compile_definitions(icu_jni PRIVATE
  ${_WIN_DEFS}
  U_USING_ICU_NAMESPACE=0
  ANDROID_LINK_SHARED_ICU4C
)
target_compile_options(icu_jni PRIVATE ${_WIN_CFLAGS} -Wno-unused-parameter "SHELL:-D__INTRODUCED_IN(x)=")
target_link_libraries(icu_jni PUBLIC icuuc icui18n base log nativehelper)

# Optional later phases


# POSIX stubs for hybrid javacore (mmap/poll/etc.) even when openjdk is off
if(NOT TARGET win64_socket_posix)
  add_library(win64_socket_posix STATIC
    "${_repo}/compat/src/win64_socket_posix.c"
    "${_repo}/compat/src/win64_posix_stubs.c"
  )
  target_include_directories(win64_socket_posix PUBLIC "${MDVM_COMPAT_INCLUDE_DIR}")
  target_compile_definitions(win64_socket_posix PRIVATE ${_WIN_DEFS} MDVM_SOCKET_NO_MACROS=1)
  target_compile_options(win64_socket_posix PRIVATE ${_WIN_CFLAGS})
  target_link_libraries(win64_socket_posix PUBLIC ws2_32)
endif()

# --- javacore (hybrid: AOSP sources + Win libcore_io stubs) ---
if(MDVM_WIN64_BUILD_JAVACORE)
  set(_JC_SRCS ${JAVACORE_SRCS})
  list(FILTER _JC_SRCS EXCLUDE REGEX "libcore_io_Linux[.]cpp$")
  list(FILTER _JC_SRCS EXCLUDE REGEX "NetworkUtilities[.]cpp$")
  list(FILTER _JC_SRCS EXCLUDE REGEX "libcore_io_AsynchronousCloseMonitor[.]cpp$")
  list(FILTER _JC_SRCS EXCLUDE REGEX "ExpatParser[.]cpp$")
  list(FILTER _JC_SRCS EXCLUDE REGEX "NativeBN[.]cpp$")
  list(FILTER _JC_SRCS EXCLUDE REGEX "cbigint[.]cpp$")
  list(FILTER _JC_SRCS EXCLUDE REGEX "android_system_OsConstantsHolder[.]cpp$")
  # NetworkUtilities uses Linux sockaddr helpers heavily; keep out for Phase B0
  # Async close monitor is Linux signal-based
  # Expat + NativeBN need extra PE deps; exclude Phase B0

  set(_JC_WIN_BRIDGE
    "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/register_libcore_io_Linux_win.cpp"
    "${_repo}/tools/win64/jni_stubs/win_path.c"
    "${_repo}/tools/win64/jni_stubs/win_fs_natives.c"
    "${_repo}/tools/win64/jni_stubs/win_net_natives.c"
    "${_repo}/tools/win64/jni_stubs/libcore_hello3.c"
  )
  set_source_files_properties("${_repo}/tools/win64/jni_stubs/libcore_hello3.c"
    PROPERTIES COMPILE_DEFINITIONS "JNI_OnLoad=javacore_stub_JNI_OnLoad_unused;JNI_OnUnload=javacore_stub_JNI_OnUnload_unused")
  # Provide empty registers for excluded modules to satisfy Register.cpp
  set(_JC_WIN_STUB_REG "${CMAKE_CURRENT_BINARY_DIR}/javacore_excluded_registers.cpp")
  file(WRITE "${_JC_WIN_STUB_REG}"
"#include <jni.h>
void register_libcore_io_AsynchronousCloseMonitor(JNIEnv*) {}
void register_libcore_math_NativeBN(JNIEnv*) {}
void register_org_apache_harmony_xml_ExpatParser(JNIEnv*) {}
void register_android_system_OsConstantsHolder(JNIEnv*) {}
")

  add_library(javacore SHARED ${_JC_SRCS} ${_JC_WIN_BRIDGE} ${_JC_WIN_STUB_REG})
  set_target_properties(javacore PROPERTIES OUTPUT_NAME "libjavacore")

  target_include_directories(javacore
    PUBLIC ${_WIN_INCLUDES}
    PUBLIC ${_ICU_COMMON_INCLUDES}
    PUBLIC "${MDVM_ICU_DIR}/libicu/ndk_headers"
    PUBLIC "${MDVM_ART_ROOT_DIR}/libziparchive/include"
    PUBLIC "${MDVM_LIBCORE_DIR}/luni/src/main/native"
    PUBLIC "${MDVM_LIBCORE_DIR}/multiplatform/windows/native"
    PRIVATE "${_repo}/tools/win64/jni_stubs"
  )
  # Prefer multipath Portability.h
  target_include_directories(javacore BEFORE PRIVATE "${MDVM_LIBCORE_DIR}/multiplatform/windows/native")
  target_compile_definitions(javacore PRIVATE
    ${_WIN_DEFS}
    U_USING_ICU_NAMESPACE=0
    LIBICU_U_SHOW_CPLUSPLUS_API=1
    ANDROID_LINK_SHARED_ICU4C
  )
  target_compile_options(javacore PRIVATE ${_WIN_CFLAGS} -Wno-unused-parameter "SHELL:-D__INTRODUCED_IN(x)=")
  # Import real ICU from this build; zip/base/log/nativehelper from phase1
  target_link_libraries(javacore PUBLIC base log nativehelper ziparchive z icuuc icui18n
    PRIVATE ws2_32 kernel32 advapi32 win64_socket_posix)
  # Also export WinNT FileSystem natives from same DLL (from win_fs)
endif()




# --- openjdkjvm (JVM_* I/O + memory for Runtime / NIO) ---
if(MDVM_WIN64_BUILD_OPENJDK)
  # Shared POSIX socket/epoll helpers may already exist for javacore
  if(NOT TARGET win64_socket_posix)
    add_library(win64_socket_posix STATIC
      "${_repo}/compat/src/win64_socket_posix.c"
      "${_repo}/compat/src/win64_posix_stubs.c"
    )
    target_include_directories(win64_socket_posix PUBLIC "${MDVM_COMPAT_INCLUDE_DIR}")
    target_compile_definitions(win64_socket_posix PRIVATE ${_WIN_DEFS} MDVM_SOCKET_NO_MACROS=1)
    target_compile_options(win64_socket_posix PRIVATE ${_WIN_CFLAGS})
    target_link_libraries(win64_socket_posix PUBLIC ws2_32)
  endif()

  add_library(openjdkjvm SHARED
    "${CMAKE_CURRENT_SOURCE_DIR}/openjdkjvm_memory_standalone.c"
  )
  set_target_properties(openjdkjvm PROPERTIES OUTPUT_NAME "libopenjdkjvm")
  target_include_directories(openjdkjvm PUBLIC
    "${MDVM_ART_ROOT_DIR}/libnativehelper/include_jni"
    "${MDVM_COMPAT_INCLUDE_DIR}"
  )
  target_compile_definitions(openjdkjvm PRIVATE ${_WIN_DEFS})
  target_link_libraries(openjdkjvm PRIVATE kernel32 psapi ws2_32 win64_socket_posix)
  set_target_properties(openjdkjvm PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS OFF)

  # --- fdlibm static ---
  add_library(fdlibm STATIC ${FDLIBM_SRCS})
  target_include_directories(fdlibm PUBLIC "${MDVM_FDLIBM_DIR}")
  target_compile_definitions(fdlibm PRIVATE ${_WIN_DEFS})
  target_compile_options(fdlibm PRIVATE -Wno-all)

  # --- openjdk hybrid: full AOSP OPENJDK_SRCS minus hard Linux-only ---
  # Phase B2: Unix/NIO channel surface + classic java.net streams.
  set(_OJ_SRCS ${OPENJDK_SRCS})
  list(FILTER _OJ_SRCS EXCLUDE REGEX "linux_close[.]cpp$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "NativeThread[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "OnLoad[.]cpp$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "LinuxNativeDispatcher[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "LinuxWatchService[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UnixCopyFile[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UnixNativeDispatcher[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UNIXProcess_md[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "EPollPort[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UnixAsynchronousServerSocketChannelImpl[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UnixAsynchronousSocketChannelImpl[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "FileSystemPreferences[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UnixDomainSockets[.]c$")
  # System/Runtime still via PE stubs (hello3 / win_runtime) to avoid ART-linked paths
  list(FILTER _OJ_SRCS EXCLUDE REGEX "UnixFileSystem_md[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "System[.]c$")
  list(FILTER _OJ_SRCS EXCLUDE REGEX "Runtime[.]c$")
  # StrictMath/Math use fdlibm — keep them

  set(_OJ_WIN
    "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/openjdk_OnLoad_win.cpp"
    "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/win_close.cpp"
    "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/NativeThread_win.c"
    "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/AsynchronousCloseMonitor_win.cpp"
    "${_repo}/tools/win64/jni_stubs/win_runtime_natives.c"
    "${_repo}/tools/win64/jni_stubs/libcore_hello3.c"
  )
  set_source_files_properties("${_repo}/tools/win64/jni_stubs/libcore_hello3.c"
    PROPERTIES COMPILE_DEFINITIONS "JNI_OnLoad=openjdk_stub_JNI_OnLoad_unused;JNI_OnUnload=openjdk_stub_JNI_OnUnload_unused")

  # Empty registers for excluded NIO.2 / process / async modules
  set(_OJ_STUB_REG "${CMAKE_CURRENT_BINARY_DIR}/openjdk_excluded_registers.cpp")
  file(WRITE "${_OJ_STUB_REG}" [=[
#include <jni.h>
extern "C" void register_java_lang_UNIXProcess(JNIEnv*) {}
extern "C" void register_java_sun_nio_fs_UnixNativeDispatcher(JNIEnv*) {}
extern "C" void register_java_util_prefs_FileSystemPreferences(JNIEnv*) {}
extern "C" void register_java_io_UnixFileSystem(JNIEnv*) {}
// Linux NIO.2 / async not registered on Windows hybrid
]=])

  add_library(openjdk SHARED ${_OJ_SRCS} ${_OJ_WIN} ${_OJ_STUB_REG})
  set_target_properties(openjdk PROPERTIES OUTPUT_NAME "libopenjdk")

  # C sources that use Android Linux code paths; do NOT define __linux__ on C++ (breaks libc++).
  set(_OJ_LINUXISH_C
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileDispatcherImpl.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileChannelImpl.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/IOUtil.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/Net.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/net_util_md.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/net_util.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/EPoll.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketChannelImpl.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/ServerSocketChannelImpl.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/DatagramChannelImpl.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/DatagramDispatcher.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/PollArrayWrapper.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileKey.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/MappedByteBuffer.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileInputStream.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/io_util_md.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketInputStream.c"
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketOutputStream.c"
  )
  set_source_files_properties(${_OJ_LINUXISH_C} PROPERTIES COMPILE_DEFINITIONS "__linux__=1")
  set_target_properties(openjdk PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS OFF)
  target_include_directories(openjdk BEFORE PRIVATE
    "${MDVM_LIBCORE_DIR}/multiplatform/windows/native"
    "${MDVM_COMPAT_INCLUDE_DIR}"
  )
  target_include_directories(openjdk PUBLIC
    ${_WIN_INCLUDES}
    ${_ICU_COMMON_INCLUDES}
    "${MDVM_LIBCORE_DIR}/ojluni/src/main/native"
    "${MDVM_LIBCORE_DIR}/luni/src/main/native"
    "${MDVM_FDLIBM_DIR}"
    "${_repo}/compat/openjdk_inc/anchor1/anchor2"
    "${MDVM_ART_ROOT_DIR}/external/boringssl/src/include"
    "${MDVM_WIN64_ENV}/lib/zlib/include"
  )
  target_compile_definitions(openjdk PRIVATE
    ${_WIN_DEFS}
    U_USING_ICU_NAMESPACE=0
    _LP64=1
  )
  target_compile_options(openjdk PRIVATE ${_WIN_CFLAGS} -Wno-unused-parameter
    -Wno-incompatible-pointer-types -Wno-int-conversion
    "SHELL:-D__INTRODUCED_IN(x)=")
  target_link_libraries(openjdk PUBLIC base log nativehelper openjdkjvm fdlibm z icuuc
    PRIVATE kernel32 advapi32 ws2_32 win64_socket_posix)
endif()



# --- boringssl libcrypto PE (L-002 Phase C0) ---
# OPENSSL_NO_ASM first: pure C, reliable clang PE. win-x86_64 .asm can be enabled later via llvm-ml.
option(MDVM_WIN64_BUILD_CRYPTO "Build real boringssl crypto PE" ON)
if(MDVM_WIN64_BUILD_CRYPTO)
  set(BORINGSSL_ROOT "${MDVM_ART_ROOT_DIR}/external/boringssl/")
  include("${BORINGSSL_ROOT}android-sources.cmake")
  # crypto_sources paths use ${BORINGSSL_ROOT} already expanded when include runs if set before include.
  # Re-include with BORINGSSL_ROOT set above.
  set(_CRYPTO_SRCS ${crypto_sources})
  # Filter out trampoline tests asm if any snuck in — crypto_sources is C-only.
  list(FILTER _CRYPTO_SRCS EXCLUDE REGEX "test/")

  add_library(crypto SHARED ${_CRYPTO_SRCS})
  set_target_properties(crypto PROPERTIES
    OUTPUT_NAME "libcrypto"
    WINDOWS_EXPORT_ALL_SYMBOLS ON
  )
  target_include_directories(crypto PUBLIC
    "${MDVM_ART_ROOT_DIR}/external/boringssl/src/include"
  )
  target_compile_definitions(crypto PRIVATE
    ${_WIN_DEFS}
    BORINGSSL_IMPLEMENTATION
    BORINGSSL_SHARED_LIBRARY
    OPENSSL_NO_ASM
    OPENSSL_SMALL
  )
  target_compile_options(crypto PRIVATE
    ${_WIN_CFLAGS}
    -Wno-unused-parameter
    -Wno-bitwise-op-parentheses
    -Wno-unknown-pragmas
  )
  target_link_libraries(crypto PRIVATE ws2_32 advapi32 bcrypt kernel32)
  # Minimal smoke tool: SHA256 of fixed string via exported C API
  add_executable(crypto_sha_smoke "${CMAKE_CURRENT_SOURCE_DIR}/crypto_sha_smoke.c")
  target_link_libraries(crypto_sha_smoke PRIVATE crypto)
  target_include_directories(crypto_sha_smoke PRIVATE "${MDVM_ART_ROOT_DIR}/external/boringssl/src/include")
endif()

message(STATUS "Win64 libcore/ICU: icu + optional javacore/openjdk hybrids + crypto")

