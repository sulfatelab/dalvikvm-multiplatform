# Phase 0 Win64 foundational graph: liblog, libbase, libnativehelper,
# libziparchive, libartpalette, libartbase — cross-built on Linux for
# x86_64-pc-windows-msvc using win64-dev-env.
#
#   source /home/agent/Projects/win64-dev-env/env.sh
#   cmake -S tools/verify/win64_phase0 -B build/win64_phase0 -G Ninja \
#     -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN \
#     -DCMAKE_BUILD_TYPE=RelWithDebInfo
#   cmake --build build/win64_phase0

cmake_minimum_required(VERSION 3.20)
project(Win64Phase0 CXX C)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "ART Win64 requires LLVM clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()
if(MSVC)
  message(FATAL_ERROR "MSVC cl/clang-cl is not supported; use plain clang++")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_C_STANDARD 11)
# Windows DLLs hide symbols by default; export all for the Phase 0 graph
# (Linux .so default visibility). Refine with .def later if needed.
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(MDVM_NATIVE_SRC_ROOT_DIR "${_repo}/vendor" CACHE PATH "Native/AOSP-like source root (multiplatform vendor/)")
set(MDVM_ART_ROOT_DIR "${_repo}/vendor" CACHE PATH "vendored art root")
set(MDVM_COMPAT_INCLUDE_DIR "${_repo}/compat/include"
    CACHE PATH "project-owned compat shims")
set(MDVM_GENSRC_DIR "${CMAKE_BINARY_DIR}/gensrc" CACHE PATH "generated sources")
set(MDVM_WIN64_ENV "$ENV{WIN64_DEV_ENV}" CACHE PATH "Win64 dev env (clang/xwin/libc++)")
if(NOT MDVM_WIN64_ENV)
  set(MDVM_WIN64_ENV "/home/agent/Projects/win64-dev-env" CACHE PATH "Win64 dev env (clang/xwin/libc++)" FORCE)
endif()

# Host-side aconfig headers (header-only stubs).
file(MAKE_DIRECTORY "${MDVM_GENSRC_DIR}")
execute_process(
  COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${_repo}/tools/bp2cmake"
          ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
          --root ${MDVM_NATIVE_SRC_ROOT_DIR}
          --art-root ${MDVM_ART_ROOT_DIR}
          --gensrc ${MDVM_GENSRC_DIR}
          --arch x86_64 --clang ${CMAKE_CXX_COMPILER} --only aconfig
  RESULT_VARIABLE _ac)
if(NOT _ac EQUAL 0)
  message(FATAL_ERROR "aconfig codegen failed (${_ac})")
endif()

# zlib (cross-built static for Win64)
set(_ZLIB_ROOT "${MDVM_WIN64_ENV}/lib/zlib")
if(NOT EXISTS "${_ZLIB_ROOT}/include/zlib.h")
  message(FATAL_ERROR "Win64 zlib not found at ${_ZLIB_ROOT}; build zlibstatic first")
endif()
add_library(z STATIC IMPORTED GLOBAL)
set_target_properties(z PROPERTIES
  IMPORTED_LOCATION "${_ZLIB_ROOT}/lib/z.lib"
  INTERFACE_INCLUDE_DIRECTORIES "${_ZLIB_ROOT}/include")

# No libcap on Windows — empty interface (libartbase overlay drops the dep).
add_library(cap INTERFACE)

# Generated phase0 graph from bp2cmake --os windows.
# POSIX-ish stubs for Win64 (pthread/dirent) used by archive libbase headers.
add_library(win64_posix_stubs STATIC
  "${_repo}/compat/src/win64_posix_stubs.c")
target_include_directories(win64_posix_stubs PRIVATE "${MDVM_COMPAT_INCLUDE_DIR}")
target_compile_definitions(win64_posix_stubs PRIVATE
  _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI)
set_target_properties(win64_posix_stubs PROPERTIES
  POSITION_INDEPENDENT_CODE ON)

include(${CMAKE_CURRENT_SOURCE_DIR}/phase0.cmake)


# Common include / define shims for all targets.
# compat/include first so our unistd.h wins over missing UCRT headers.
get_property(_all_targets DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" PROPERTY BUILDSYSTEM_TARGETS)
set(_WIN_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_win64_prelude.h")
foreach(_t IN LISTS _all_targets)
  get_target_property(_ttype ${_t} TYPE)
  if(_ttype STREQUAL "INTERFACE_LIBRARY" OR _ttype STREQUAL "UTILITY")
    continue()
  endif()
  target_include_directories(${_t} BEFORE PRIVATE
    "${MDVM_COMPAT_INCLUDE_DIR}")
  target_include_directories(${_t} PRIVATE
    "${MDVM_GENSRC_DIR}/art/aconfig/include")
  target_compile_definitions(${_t} PRIVATE
    _CRT_SECURE_NO_WARNINGS
    NOMINMAX
    WIN32_LEAN_AND_MEAN)
  target_compile_options(${_t} PRIVATE
    "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_WIN_PRELUDE}>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-unused-command-line-argument>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-deprecated-declarations>")
  if(NOT _t STREQUAL "win64_posix_stubs")
    target_link_libraries(${_t} win64_posix_stubs)
  endif()
endforeach()

# Per-file drift shims.
if(TARGET base)
  set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    PROPERTIES COMPILE_OPTIONS "-include;cstdint")
  set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/fmtlib/src/format.cc
    PROPERTIES COMPILE_OPTIONS "-fexceptions;-UNDEBUG")
endif()

message(STATUS "Win64 Phase 0: targets log base nativehelper ziparchive artpalette artbase")
