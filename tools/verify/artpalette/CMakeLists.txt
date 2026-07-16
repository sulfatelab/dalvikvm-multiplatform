# Verification harness: first ART core module (libartpalette).
# Proves the Layer 1 ART extensions (art_defaults inheritance, soong_config
# source_build re-enable, avx2/codegen select collapsing) yield a buildable
# target. libartpalette is the only ART leaf with NO generated sources, so it
# validates the ART path without the codegen pipeline (next step).

cmake_minimum_required(VERSION 3.16)
project(VerifyArtPalette CXX C)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "This build requires clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)

set(MDVM_NATIVE_SRC_ROOT_DIR "/home/agent/Projects/MinDalvikVM-Archive/native")
set(MDVM_COMPAT_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../compat/include")

include(${CMAKE_CURRENT_SOURCE_DIR}/artpalette.cmake)

# Toolchain-drift shim (harness only): libbase/hex.cpp needs <cstdint> on
# clang-21. See toolchain-drift memory.
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    PROPERTIES COMPILE_OPTIONS "-include;cstdint"
)
