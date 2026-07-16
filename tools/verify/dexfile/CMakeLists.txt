# Verification harness: libdexfile — operator_out gensrcs + depends on libartbase.
# Key validation: the art.go PUBLIC defines (stack gaps / frame limit) reach
# dexfile THROUGH its link to artbase, without being restated -- proving the
# PUBLIC-define propagation channel works across the link boundary.

cmake_minimum_required(VERSION 3.16)
project(VerifyDexfile CXX C)

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

include(${CMAKE_CURRENT_SOURCE_DIR}/dexfile.cmake)

# Toolchain-drift shims (harness only; see toolchain-drift memory).
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    PROPERTIES COMPILE_OPTIONS "-include;cstdint"
)
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/metrics/metrics_common.cc
    PROPERTIES COMPILE_OPTIONS "-include;algorithm"
)
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/file_utils.cc
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/utils.cc
    PROPERTIES COMPILE_OPTIONS "-Wno-strict-primary-template-shadow"
)
# libdexfile dex/*.cc use std::copy_n + the stl_util Filter shadow; the generated
# dexfile operator_out.cc includes headers using uint32_t. Apply both shims.
file(GLOB _DEX_CC ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libdexfile/dex/*.cc)
set_source_files_properties(
    ${_DEX_CC}
    PROPERTIES COMPILE_OPTIONS "-include;cstdint;-include;algorithm;-Wno-strict-primary-template-shadow"
)
file(GLOB_RECURSE _DEX_GEN ${MDVM_GENSRC_DIR}/art/libdexfile/*.operator_out.cc)
# (generated files may not exist at configure time; the dexfile target adds the
# include dir so they compile, but uint32_t needs cstdint -- handle via a target
# property on dexfile below if needed.)
target_compile_options(dexfile PRIVATE -include cstdint)
