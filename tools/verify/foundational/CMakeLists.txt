# Verification harness for the 8 bp2cmake-generated foundational libraries.
#
# Mirrors the archive's native/cmake/CMakeLists.txt top-level: build the
# foundational libs together with the real (converted) liblog -- no stub. Proves
# the generated descriptions compile AND link against each other.

cmake_minimum_required(VERSION 3.16)
project(VerifyFoundational CXX C)

# Repo root = tools/verify/<harness>/../../..
get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

# ART must be built with clang (clang-only warning flags; see bp2cmake_linux_scope.md).
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "This build requires clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)

set(MDVM_NATIVE_SRC_ROOT_DIR "${_repo}/vendor" CACHE PATH "Native/AOSP-like source root (multiplatform vendor/)")
# Project-owned compat include root (vendored shims, e.g. gtest/gtest_prod.h).
set(MDVM_COMPAT_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../compat/include")

# --- Toolchain-compat shim (verify harness ONLY) ---------------------------
# 2023 sources vs clang-21/newer-libc++ drift (see memory + libbase RESULT.md):
# a handful of TUs use uint8_t/size_t without including <cstdint>/<cstddef>.
# Force-include them for the specific drifting files. NOT in bp2cmake/overlay;
# vanishes on submodule bump. Scoped per-file so we don't disturb sources with
# deliberate macro ordering (e.g. posix_strerror_r.cpp's #undef _GNU_SOURCE).
set(_DRIFT_CSTDINT
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libprocinfo/process.cpp
)

# The generated descriptions. The generated file references targets log, base,
# z, etc.; we provide host zlib as `z` below before including.
# Host system zlib stands in for AOSP's in-tree libz (audit 5.2 item 6).
find_package(ZLIB REQUIRED)
add_library(z INTERFACE)
target_link_libraries(z INTERFACE ZLIB::ZLIB)

include(${CMAKE_CURRENT_SOURCE_DIR}/foundational.cmake)

# Apply the per-file drift shim after targets exist.
set_source_files_properties(
    ${_DRIFT_CSTDINT}
    PROPERTIES COMPILE_OPTIONS "-include;cstdint"
)
