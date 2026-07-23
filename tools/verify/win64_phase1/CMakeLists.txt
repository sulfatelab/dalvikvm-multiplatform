# Phase 1 Win64: libart + dalvikvm skeleton (gate: -showversion).
# Cross-build on Linux with win64-dev-env.

cmake_minimum_required(VERSION 3.20)
project(Win64Phase1 CXX C ASM)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "Need LLVM clang (got ${CMAKE_CXX_COMPILER_ID})")
endif()
if(MSVC)
  message(FATAL_ERROR "MSVC cl/clang-cl not supported")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_C_STANDARD 11)
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
# Pure multipath vendor/ layout (L-006). Generated phase1.cmake resolves
# sources via ${MDVM_NATIVE_SRC_ROOT_DIR}/... — never a sibling archive tree.
# Override only for experiments; product default is in-tree vendor/.
set(MDVM_NATIVE_SRC_ROOT_DIR "${_repo}/vendor" CACHE PATH "Native/AOSP-like source root (multiplatform vendor/)")
set(MDVM_ART_ROOT_DIR "${_repo}/vendor" CACHE PATH "")
set(MDVM_ART_DIR "${_repo}/vendor/art" CACHE PATH "Nested ART tree (artmp_*)")
set(MDVM_COMPAT_INCLUDE_DIR "${_repo}/compat/include" CACHE PATH "")
set(MDVM_GENSRC_DIR "${CMAKE_BINARY_DIR}/gensrc" CACHE PATH "")
set(MDVM_WIN64_ENV "$ENV{WIN64_DEV_ENV}" CACHE PATH "Win64 dev env (clang/xwin/libc++)")
if(NOT MDVM_WIN64_ENV)
  set(MDVM_WIN64_ENV "/home/agent/Projects/win64-dev-env" CACHE PATH "Win64 dev env (clang/xwin/libc++)" FORCE)
endif()
# Folded from former compat/windows/art into nested ART multipath paths.
set(MDVM_ART_WIN_RUNTIME "${MDVM_ART_DIR}/runtime/multiplatform/windows" CACHE PATH "")
set(MDVM_ART_WIN_STUBS "${MDVM_ART_DIR}/multiplatform/windows" CACHE PATH "")
set(MDVM_ART_WIN_OPENJDKJVM "${MDVM_ART_DIR}/openjdkjvm" CACHE PATH "")

file(MAKE_DIRECTORY "${MDVM_GENSRC_DIR}")

# aconfig + mterp + asm_defines (host Python/codegen; asm_defines uses host clang)
# Codegen runs on the *build* host. Prefer a native Linux clang++ even when
# CMAKE_CXX_COMPILER is a Windows-target clang (cross builds).
find_program(MDVM_HOST_CLANGXX NAMES clang++ REQUIRED)
execute_process(
  COMMAND ${MDVM_HOST_CLANGXX} -print-resource-dir
  OUTPUT_VARIABLE MDVM_HOST_CLANG_RESOURCE_DIR
  OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
foreach(_kind aconfig mterp asm_defines)
  execute_process(
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${_repo}/tools/bp2cmake"
            ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
            --root ${MDVM_NATIVE_SRC_ROOT_DIR}
            --art-root ${MDVM_ART_ROOT_DIR}
            --gensrc ${MDVM_GENSRC_DIR}
            --arch x86_64 --clang ${MDVM_HOST_CLANGXX} --os windows
            --target-include ${MDVM_WIN64_ENV}/lib/libcxx/include/c++/v1
            --target-include ${MDVM_HOST_CLANG_RESOURCE_DIR}/include
            --target-include ${MDVM_WIN64_ENV}/xwin/sdk/include/ucrt
            --target-include ${MDVM_WIN64_ENV}/xwin/sdk/include/shared
            --target-include ${MDVM_WIN64_ENV}/xwin/sdk/include/um
            --target-include ${MDVM_WIN64_ENV}/xwin/crt/include
            --only ${_kind}
    RESULT_VARIABLE _rc)
  if(NOT _rc EQUAL 0)
    message(FATAL_ERROR "codegen ${_kind} failed (${_rc})")
  endif()
endforeach()

# Catch host-layout asm_defines regeneration before it reaches Win64 trampolines.
# In this ART revision Runtime::instrumentation_ is at 0x328 for PE and 0x340
# for Linux; using the latter crashes generic-JNI exit handling.
set(_asm_defines_header "${MDVM_GENSRC_DIR}/art/asm/include/asm_defines.h")
file(STRINGS "${_asm_defines_header}" _instrumentation_offset
     REGEX "^#define RUNTIME_INSTRUMENTATION_OFFSET " LIMIT_COUNT 1)
if(NOT _instrumentation_offset STREQUAL
       "#define RUNTIME_INSTRUMENTATION_OFFSET 0x328")
  message(FATAL_ERROR
    "Win64 asm_defines has the wrong Runtime instrumentation offset: "
    "${_instrumentation_offset}")
endif()

# zlib
set(_ZLIB_ROOT "${MDVM_WIN64_ENV}/lib/zlib")
add_library(z STATIC IMPORTED GLOBAL)
set_target_properties(z PROPERTIES
  IMPORTED_LOCATION "${_ZLIB_ROOT}/lib/z.lib"
  INTERFACE_INCLUDE_DIRECTORIES "${_ZLIB_ROOT}/include")

# lz4
set(_LZ4_ROOT "${MDVM_WIN64_ENV}/lib/lz4")
add_library(lz4 STATIC IMPORTED GLOBAL)
set_target_properties(lz4 PROPERTIES
  IMPORTED_LOCATION "${_LZ4_ROOT}/lib/lz4.lib"
  INTERFACE_INCLUDE_DIRECTORIES "${_LZ4_ROOT}/include")

add_library(cap INTERFACE)
add_library(expat INTERFACE)

# POSIX stubs
add_library(win64_posix_stubs STATIC "${_repo}/compat/src/win64_posix_stubs.c")
target_include_directories(win64_posix_stubs PRIVATE "${MDVM_COMPAT_INCLUDE_DIR}")
target_compile_definitions(win64_posix_stubs PRIVATE
  _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI)
set_target_properties(win64_posix_stubs PROPERTIES POSITION_INDEPENDENT_CODE ON)

include(${CMAKE_CURRENT_SOURCE_DIR}/phase1.cmake)

# Ensure sigchain exists (not always emitted in dependency closure).
if(NOT TARGET sigchain)
  add_library(sigchain SHARED "${MDVM_ART_WIN_RUNTIME}/sigchain_windows.cc")
  target_include_directories(sigchain PUBLIC "${MDVM_ART_ROOT_DIR}/art/sigchainlib" "${MDVM_COMPAT_INCLUDE_DIR}")
  target_compile_definitions(sigchain PRIVATE _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI CHAR_BIT=8)
  set_target_properties(sigchain PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
endif()

# Inject Windows OS sources into art + sigchain
if(TARGET art)
  target_sources(art PRIVATE
    "${MDVM_ART_WIN_RUNTIME}/thread_windows.cc"
    "${MDVM_ART_WIN_RUNTIME}/runtime_windows.cc"
    "${MDVM_ART_WIN_RUNTIME}/monitor_windows.cc"
    "${MDVM_ART_WIN_OPENJDKJVM}/openjdkjvm_memory_windows.cc")
endif()
if(TARGET sigchain)
  target_sources(sigchain PRIVATE
    "${MDVM_ART_WIN_RUNTIME}/sigchain_windows.cc")
  target_include_directories(sigchain PUBLIC
    "${MDVM_ART_ROOT_DIR}/art/sigchainlib")
endif()
if(TARGET procinfo)
  target_sources(procinfo PRIVATE
    "${MDVM_ART_WIN_STUBS}/procinfo_process_stub.cpp")
endif()
if(TARGET unwindstack)
  target_sources(unwindstack PRIVATE
    "${MDVM_ART_WIN_STUBS}/AsmGetRegs_stub.c")
endif()
if(TARGET dexfile)
  # Ensure art_api::dex g_ADexFile_* symbols exist for unwindstack.
  target_sources(dexfile PRIVATE
    "${MDVM_ART_ROOT_DIR}/art/libdexfile/external/dex_file_supp.cc")
endif()
if(TARGET lzma)
  target_sources(lzma PRIVATE
    "${MDVM_ART_WIN_STUBS}/lzma_aes_stub.c")
  # Keep portable C AES (Aes.c) only; don't probe AES-NI.
  target_compile_definitions(lzma PRIVATE MY_CPU_X86_OR_AMD64=0)
endif()

set(_WIN_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_win64_prelude.h")
get_property(_all_targets DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" PROPERTY BUILDSYSTEM_TARGETS)
foreach(_t IN LISTS _all_targets)
  get_target_property(_ttype ${_t} TYPE)
  if(_ttype STREQUAL "INTERFACE_LIBRARY" OR _ttype STREQUAL "UTILITY")
    continue()
  endif()
  target_include_directories(${_t} BEFORE PRIVATE "${MDVM_COMPAT_INCLUDE_DIR}")
  target_include_directories(${_t} PRIVATE "${_repo}/vendor/nativehelper-headers")
  target_include_directories(${_t} PRIVATE
    "${MDVM_GENSRC_DIR}/art/aconfig/include"
    "${MDVM_GENSRC_DIR}/art/asm/include"
    "${MDVM_WIN64_ENV}/third_party/lz4/lib")
  target_compile_definitions(${_t} PRIVATE
    _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI
    _WIN32_WINNT=0x0A00 NTDDI_VERSION=NTDDI_WIN10_RS4)
  target_compile_options(${_t} PRIVATE
    "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_WIN_PRELUDE}>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-unused-command-line-argument>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-deprecated-declarations>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-sign-conversion>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-shorten-64-to-32>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=sign-conversion>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=shorten-64-to-32>")
  if(NOT _t STREQUAL "win64_posix_stubs")
    target_link_libraries(${_t} win64_posix_stubs)
  endif()
  target_link_libraries(${_t} ws2_32 synchronization)
endforeach()

# MapViewOfFile3 is a Windows 10 RS4 API imported through onecore.lib.
if(TARGET artbase)
  target_link_libraries(artbase onecore)
endif()

# Per-file shims
if(TARGET base)
  set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    PROPERTIES COMPILE_OPTIONS "-include;cstdint")
  set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/fmtlib/src/format.cc
    PROPERTIES COMPILE_OPTIONS "-fexceptions;-UNDEBUG")
endif()

# ART_TARGET_WINDOWS must reach art + consumers
foreach(_t art dalvikvm artbase dexfile)
  if(TARGET ${_t})
    target_compile_definitions(${_t} PUBLIC ART_TARGET ART_TARGET_WINDOWS)
  endif()
endforeach()

# lzma AesOpt needs AES-NI target feature under clang.
if(TARGET lzma)
  set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/external/lzma/C/AesOpt.c
    PROPERTIES COMPILE_OPTIONS "-maes;-msse4.1")
endif()

message(STATUS "Win64 Phase 1: art + dalvikvm (showversion gate)")

# Strip Linux-only linker flags that break lld-link.
get_property(_all_targets DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" PROPERTY BUILDSYSTEM_TARGETS)
foreach(_t IN LISTS _all_targets)
  get_target_property(_ttype ${_t} TYPE)
  if(_ttype STREQUAL "INTERFACE_LIBRARY" OR _ttype STREQUAL "UTILITY")
    continue()
  endif()
  get_target_property(_lo ${_t} LINK_OPTIONS)
  if(_lo)
    list(FILTER _lo EXCLUDE REGEX "max-page-size|-z")
    set_property(TARGET ${_t} PROPERTY LINK_OPTIONS "${_lo}")
  endif()
endforeach()

# Use Windows cpu_features implementation instead of Linux.
if(TARGET art)
  get_target_property(_arts art SOURCES)
  if(_arts)
    list(FILTER _arts EXCLUDE REGEX "impl_x86_linux_or_android.c$")
    set_property(TARGET art PROPERTY SOURCES ${_arts})
  endif()
  target_sources(art PRIVATE
    "${MDVM_NATIVE_SRC_ROOT_DIR}/external/cpu_features/src/impl_x86_windows.c")
  target_compile_definitions(art PRIVATE CPU_FEATURES_OS_WINDOWS=1)
endif()
