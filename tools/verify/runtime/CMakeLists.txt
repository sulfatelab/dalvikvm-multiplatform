# Verify harness: libart (the runtime) + full dep graph.
# Generation split:
#   - operator_out (art_operator_srcs): emitter add_custom_command (30 files,
#     true list read from the .bp).
#   - mterp_<arch>.S + asm_defines.h: the Python codegen driver, run at
#     configure time below (the emitter cannot express the two-stage asm_defines
#     compile nor the mterp generation).

cmake_minimum_required(VERSION 3.16)
project(VerifyRuntime CXX C ASM)

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
set(MDVM_BP2CMAKE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/bp2cmake")

# Run the Python codegen driver for mterp + asm_defines (configure-time). The
# operator_out files are produced by the emitter's add_custom_commands.
execute_process(
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${MDVM_BP2CMAKE}"
            ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
            --root ${MDVM_NATIVE_SRC_ROOT_DIR} --gensrc ${MDVM_GENSRC_DIR}
            --arch x86_64 --clang clang++ --only mterp
    RESULT_VARIABLE _mterp_rc)
if(NOT _mterp_rc EQUAL 0)
    message(FATAL_ERROR "mterp codegen failed (${_mterp_rc})")
endif()
execute_process(
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${MDVM_BP2CMAKE}"
            ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
            --root ${MDVM_NATIVE_SRC_ROOT_DIR} --gensrc ${MDVM_GENSRC_DIR}
            --arch x86_64 --clang clang++ --only asm_defines
    RESULT_VARIABLE _asm_rc)
if(NOT _asm_rc EQUAL 0)
    message(FATAL_ERROR "asm_defines codegen failed (${_asm_rc})")
endif()

find_package(ZLIB REQUIRED)
add_library(z INTERFACE)
target_link_libraries(z INTERFACE ZLIB::ZLIB)
add_library(cap INTERFACE)
set_target_properties(cap PROPERTIES
    INTERFACE_LINK_LIBRARIES "/usr/lib/x86_64-linux-gnu/libcap.so")
# liblz4: host system lib (no submodule in the archive; runtime links it).
add_library(lz4 INTERFACE)
set_target_properties(lz4 PROPERTIES
    INTERFACE_LINK_LIBRARIES "/usr/lib/x86_64-linux-gnu/liblz4.so.1")

include(${CMAKE_CURRENT_SOURCE_DIR}/runtime.cmake)

# --- Toolchain-drift shims (harness only) -----------------------------------
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
target_compile_options(dexfile PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")
target_compile_options(elffile PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>" "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>")
target_compile_options(profile PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>" "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>")
# unwindstack has AsmGetRegsX86_64.S -> scope the prelude to C/CXX only.
target_compile_options(unwindstack PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")
target_compile_options(odrstatslog PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>" "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>")
target_compile_options(nativeloader PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>" "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>")
target_compile_options(nativebridge PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")
# dalvikvm executable: 1 .cc, links libart. Prelude for clang-21 drift.
target_compile_options(dalvikvm PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")
target_compile_definitions(dalvikvm PRIVATE ANDROID_HOST_MUSL)
# libart: 237 srcs; broadly apply the prelude + shadow demotion (clang-21 drift).
# Scope to C/CXX only -- the .S assembly sources must NOT get -include <stdint.h>
# (the assembler-with-cpp frontend chokes on the C headers). ASM still gets the
# target's include dirs (asm_support_x86_64.S, gensrc asm_defines.h) it needs.
target_compile_options(art PRIVATE
    "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>")
# glibc 2.38 now declares strlcpy, conflicting with ART's host shim in
# base/strlcpy.h (guarded for non-bionic/non-musl). The shim skips itself when
# ANDROID_HOST_MUSL is defined; glibc-with-strlcpy behaves like musl here, so
# set it to use the libc strlcpy. Harness-only toolchain-drift shim.
target_compile_definitions(art PRIVATE ANDROID_HOST_MUSL)
