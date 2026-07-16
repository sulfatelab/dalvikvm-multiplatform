# Verification harness for the bp2cmake-generated libbase.
#
# Proves the generated CMake actually compiles: it builds every libbase
# translation unit with the generated include dirs + flags and links base.so.
#
# `log` (liblog) is the next module to convert; here it is a minimal stub so the
# libbase prototype can be validated in isolation. We deliberately do NOT set
# --no-undefined in this harness, so base.so may carry unresolved __android_log_*
# symbols that the real liblog will satisfy later (exactly the archive's model).

cmake_minimum_required(VERSION 3.16)
project(VerifyLibbase CXX C)

# ART must be built with clang/clang++ (the archive forces this via
# -DCMAKE_C_COMPILER=clang). Several cflags (-Wexit-time-destructors,
# -Wthread-safety) are clang-only, so g++ cannot build this tree.
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "This build requires clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)

# Point at the archive's native source tree (2023 pins — our prototype baseline).
set(MDVM_NATIVE_SRC_ROOT_DIR "/home/agent/Projects/MinDalvikVM-Archive/native")

# Stub liblog so the `base` target's link dependency resolves.
add_library(log SHARED stub_log.c)
target_include_directories(log PUBLIC ${MDVM_NATIVE_SRC_ROOT_DIR}/logging/liblog/include)

# The generated description of libbase.
include(${CMAKE_CURRENT_SOURCE_DIR}/libbase.cmake)

# --- Toolchain-compat shim (verify harness ONLY) ---------------------------
# The archive's sources are pinned to ~2023 AOSP and were built with clang ~14.
# clang-21 / newer libc++ no longer transitively include <cstdint>, so hex.cpp
# (which uses uint8_t) fails to compile. This is 2023-source vs 2026-toolchain
# DRIFT, not a converter defect, and it disappears once we bump submodules (the
# project's actual goal). We force-include <cstdint> for that ONE file so the
# prototype can prove the generated build compiles+links end to end.
#
# Scoped to hex.cpp only: a global -include would precede posix_strerror_r.cpp's
# deliberate `#undef _GNU_SOURCE` and wrongly select glibc's GNU strerror_r.
# This shim lives in the verify harness, NOT in bp2cmake or the overlay.
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    PROPERTIES COMPILE_OPTIONS "-include;cstdint"
)
