# Verify harness: libart's leaf dependencies + everything below them.
# 8 foundational + artpalette/artbase/dexfile/elffile/profile + the 5 runtime
# deps (sigchain, nativebridge, nativeloader, odrstatslog, unwindstack).
# Proves the whole pre-runtime graph configures, compiles, and links.

cmake_minimum_required(VERSION 3.16)
project(VerifyArtDeps CXX C)

# Repo root = tools/verify/<harness>/../../..
get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "This build requires clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(MDVM_NATIVE_SRC_ROOT_DIR "${_repo}/vendor" CACHE PATH "Native/AOSP-like source root (multiplatform vendor/)")
set(MDVM_COMPAT_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../compat/include")
set(MDVM_GENSRC_DIR "${CMAKE_BINARY_DIR}/gensrc")

find_package(ZLIB REQUIRED)
add_library(z INTERFACE)
target_link_libraries(z INTERFACE ZLIB::ZLIB)
add_library(cap INTERFACE)
set_target_properties(cap PROPERTIES
    INTERFACE_LINK_LIBRARIES "/usr/lib/x86_64-linux-gnu/libcap.so")

include(${CMAKE_CURRENT_SOURCE_DIR}/artdeps.cmake)

# --- Toolchain-drift shims (harness only; see toolchain-drift memory) -------
set(_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_toolchain_prelude.h")
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libprocinfo/process.cpp
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/metrics/metrics_common.cc
    PROPERTIES COMPILE_OPTIONS "-include;${_PRELUDE}"
)
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/file_utils.cc
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/utils.cc
    PROPERTIES COMPILE_OPTIONS "-Wno-strict-primary-template-shadow"
)
file(GLOB _DEX_CC ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libdexfile/dex/*.cc)
set_source_files_properties(
    ${_DEX_CC}
    PROPERTIES COMPILE_OPTIONS "-include;${_PRELUDE};-Wno-strict-primary-template-shadow"
)
target_compile_options(dexfile PRIVATE "SHELL:-include ${_PRELUDE}")
target_compile_options(elffile PRIVATE "SHELL:-include ${_PRELUDE}" -Wno-strict-primary-template-shadow)
target_compile_options(profile PRIVATE "SHELL:-include ${_PRELUDE}" -Wno-strict-primary-template-shadow)
# unwindstack: 34 srcs; some use uint*_t / std::copy without includes on clang-21.
target_compile_options(unwindstack PRIVATE "SHELL:-include ${_PRELUDE}")
# odrstatslog / nativeloader / nativebridge include art headers.
target_compile_options(odrstatslog PRIVATE "SHELL:-include ${_PRELUDE}" -Wno-strict-primary-template-shadow)
target_compile_options(nativeloader PRIVATE "SHELL:-include ${_PRELUDE}" -Wno-strict-primary-template-shadow)
target_compile_options(nativebridge PRIVATE "SHELL:-include ${_PRELUDE}")
