# Verification harness: libartbase — first ART module with generated sources.
# Validates the gensrcs pipeline (operator_out codegen via add_custom_command)
# AND the art.go-injected PUBLIC defines (stack-overflow gaps / frame limit)
# end to end: configure + compile + link.

cmake_minimum_required(VERSION 3.16)
project(VerifyArtBase CXX C)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "This build requires clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(MDVM_NATIVE_SRC_ROOT_DIR "/home/agent/Projects/MinDalvikVM-Archive/native")
set(MDVM_COMPAT_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../compat/include")
set(MDVM_GENSRC_DIR "${CMAKE_BINARY_DIR}/gensrc")

# Host zlib stands in for AOSP libz (audit 5.2 item 6).
find_package(ZLIB REQUIRED)
add_library(z INTERFACE)
target_link_libraries(z INTERFACE ZLIB::ZLIB)

# Host libcap for base/utils.cc (capget/capset). libartbase static_libs libcap.
add_library(cap INTERFACE)
set_target_properties(cap PROPERTIES
    INTERFACE_LINK_LIBRARIES "/usr/lib/x86_64-linux-gnu/libcap.so")

include(${CMAKE_CURRENT_SOURCE_DIR}/artbase.cmake)

# Toolchain-drift shims (harness only): files needing extra includes / warning
# demotions on clang-21 vs the 2023 sources. See toolchain-drift memory; these
# vanish on submodule bump and are NOT converter/overlay concerns.
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    PROPERTIES COMPILE_OPTIONS "-include;cstdint"
)
# metrics_common.cc: metrics.h uses std::all_of without <algorithm> on newer libc++.
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/metrics/metrics_common.cc
    PROPERTIES COMPILE_OPTIONS "-include;algorithm"
)
# file_utils.cc + utils.cc include stl_util.h, whose `Filter` shadows a template
# param -- a hard error in clang-21 (-Wstrict-primary-template-shadow), only a
# warning when these 2023 sources were written. Demote to non-error.
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/file_utils.cc
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/utils.cc
    PROPERTIES COMPILE_OPTIONS "-Wno-strict-primary-template-shadow"
)
