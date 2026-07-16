# Combined harness: all converted modules through the ART mid-tier.
# foundational (base/log/nativehelper/procinfo/ziparchive/tinyxml2/lzma/
# cpu_features) + ART (artpalette/artbase/dexfile/elffile/profile).
# Proves the whole converted graph-so-far configures, compiles, and links.

cmake_minimum_required(VERSION 3.16)
project(VerifyArtCore CXX C)

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

include(${CMAKE_CURRENT_SOURCE_DIR}/artcore.cmake)

# --- Toolchain-drift shims (harness only; see toolchain-drift memory) -------
# clang-21 vs 2023 sources: missing <cstdint>/<algorithm>, and the stl_util.h
# Filter template-shadow hard error. A single -include of the compat prelude
# (cstdint+cstddef+algorithm) avoids the repeated-include de-dup problem. NEVER
# applied to posix_strerror_r.cpp (force-include would lock in _GNU_SOURCE
# before its #undef). Vanishes on submodule bump.
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
# Generated operator_out.cc (dexfile/artbase) and elffile/profile TUs: prelude
# via target options. "SHELL:" keeps the -include/<path> pair intact here
# (target_compile_options de-dups otherwise; set_source_files_properties above
# does not, so the plain ;-list form is used there).
target_compile_options(dexfile PRIVATE "SHELL:-include ${_PRELUDE}")
target_compile_options(elffile PRIVATE "SHELL:-include ${_PRELUDE}" -Wno-strict-primary-template-shadow)
target_compile_options(profile PRIVATE "SHELL:-include ${_PRELUDE}" -Wno-strict-primary-template-shadow)
