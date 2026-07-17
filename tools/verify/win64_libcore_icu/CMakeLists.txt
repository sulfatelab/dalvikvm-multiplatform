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

option(MDVM_WIN64_BUILD_JAVACORE "Build real libjavacore PE (experimental)" OFF)
option(MDVM_WIN64_BUILD_OPENJDK "Build real libopenjdk PE (experimental)" OFF)

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
if(MDVM_WIN64_BUILD_JAVACORE)
  message(STATUS "javacore PE: experimental — expect Linux-only compile failures")
  add_library(javacore SHARED ${JAVACORE_SRCS})
  target_include_directories(javacore PUBLIC
    ${_WIN_INCLUDES}
    ${_ICU_COMMON_INCLUDES}
    "${MDVM_ICU_DIR}/libicu/ndk_headers"
    "${MDVM_ART_ROOT_DIR}/libziparchive/include"
    "${MDVM_ART_ROOT_DIR}/external/boringssl/src/include"
  )
  target_compile_definitions(javacore PRIVATE
    ${_WIN_DEFS}
    U_USING_ICU_NAMESPACE=0
    LIBICU_U_SHOW_CPLUSPLUS_API=1
  )
  target_compile_options(javacore PRIVATE "SHELL:-D__INTRODUCED_IN(x)=")
  target_link_libraries(javacore PUBLIC base log nativehelper icuuc ziparchive z)
endif()

message(STATUS "Win64 libcore/ICU Phase A: icuuc + icui18n + icu_jni")
