# Top-level native build for the minimal ART runtime (dalvikvm) on GNU/Linux.
#
# This is the SINGLE entry point: it builds the whole dalvikvm graph (18 targets)
# from generated/dalvikvm.cmake, which is produced by ./generate.sh from nested
# vendor/ Android.bp via the bp2cmake converter. This file itself is the only
# hand-written CMake -- project-owned glue that the converter cannot derive:
#   - host/system imported libs (z, cap, lz4)
#   - the Python codegen driver invocation (mterp + asm_defines)
#   - toolchain-drift shims for the 2023 sources under clang-21 (see RESULT docs)
#
# Configure with clang and a build type:
#   cmake -S native -B build/native -G Ninja \
#     -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=RelWithDebInfo

cmake_minimum_required(VERSION 3.16)
project(MinDalvikVM CXX C ASM)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "ART must be built with clang/clang++ (got ${CMAKE_CXX_COMPILER_ID})")
endif()

# android-16.0.0_r4 art relies on Soong's C++20 default (e.g. disassembler_x86.cc
# uses std::ostringstream::view(), a C++20 method). Older 2023 pins built at
# C++17; current art needs C++20. Modules that set their own cpp_std in the .bp
# still get a per-target -std= from the emitter, overriding this.
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_C_STANDARD 11)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

# --- Paths (override on the command line as needed) -------------------------
get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
set(MDVM_NATIVE_SRC_ROOT_DIR "${_repo}/vendor"
    CACHE PATH "AOSP native source tree (submodules)")
set(MDVM_COMPAT_INCLUDE_DIR "${_repo}/compat/include"
    CACHE PATH "Project-owned compat shim headers")
set(MDVM_BP2CMAKE "${_repo}/tools/bp2cmake" CACHE PATH "converter package dir")
set(MDVM_GENSRC_DIR "${CMAKE_BINARY_DIR}/gensrc")
# Extra source trees. art + libcore are bumped to android-16.0.0_r4 in the
# project-owned vendor/ tree (resolves the libart<->libcore skew); the rest come
# from nested vendor/ where present. MDVM_ART_ROOT_DIR is vendor/ itself because art
# module paths keep their `art/...` prefix.
set(MDVM_ART_ROOT_DIR "${_repo}/vendor" CACHE PATH "vendored art snapshot root")
set(MDVM_LIBCORE_DIR "${_repo}/vendor/libcore" CACHE PATH "vendored libcore tree")
# A16 art compiles against newer libnativehelper header-only headers (utils.h +
# ScopedUtfChars' string_view conversion). vendor-sync fetches them here; put
# first on art's include path.
set(MDVM_NATIVEHELPER_HDRS_DIR "${_repo}/vendor/nativehelper-headers"
    CACHE PATH "vendored A16 libnativehelper header-only headers")
set(MDVM_ICU_DIR "${_repo}/vendor/icu" CACHE PATH "ICU tree (nested vendor/icu)")
set(MDVM_FDLIBM_DIR "${_repo}/vendor/java-external/fdlibm" CACHE PATH "fdlibm tree (nested)")

# --- Code generation (replaces historical Gradle tasks) --------------------
# operator_out is emitted as add_custom_commands inside the generated file; the
# aconfig headers + two-stage asm_defines + mterp are run here at configure time.
# art/* inputs come from nested vendor/art (--art-root).
foreach(_kind aconfig mterp asm_defines)
    execute_process(
        COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${MDVM_BP2CMAKE}"
                ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
                --root ${MDVM_NATIVE_SRC_ROOT_DIR} --art-root ${MDVM_ART_ROOT_DIR}
                --libcore-root ${MDVM_LIBCORE_DIR}
                --gensrc ${MDVM_GENSRC_DIR}
                --arch x86_64 --clang ${CMAKE_CXX_COMPILER} --only ${_kind}
        RESULT_VARIABLE _rc)
    if(NOT _rc EQUAL 0)
        message(FATAL_ERROR "codegen '${_kind}' failed (${_rc})")
    endif()
endforeach()

# --- Host/system imported libraries -----------------------------------------
# These replace AOSP in-tree libz/liblzma-host/libcap/liblz4 (audit 5.2 item 6).
find_package(ZLIB REQUIRED)
add_library(z INTERFACE)
target_link_libraries(z INTERFACE ZLIB::ZLIB)
foreach(_hostlib cap lz4)
    find_library(_${_hostlib}_path NAMES ${_hostlib} REQUIRED)
    add_library(${_hostlib} INTERFACE)
    set_target_properties(${_hostlib} PROPERTIES INTERFACE_LINK_LIBRARIES "${_${_hostlib}_path}")
endforeach()
# expat: host system lib (no AOSP submodule); libjavacore links it.
find_library(_expat_path NAMES expat expatw REQUIRED)
add_library(expat INTERFACE)
set_target_properties(expat PROPERTIES INTERFACE_LINK_LIBRARIES "${_expat_path}")

# --- The generated graph (18 targets, deps-first) ---------------------------
include(${CMAKE_CURRENT_SOURCE_DIR}/generated/dalvikvm.cmake)

# --- Toolchain-drift shims (2023 sources vs clang-21; harness-level only) ----
# These compensate for source/toolchain drift and disappear when submodules are
# bumped to current AOSP. NONE of this is in the converter or the overlay. See
# tools/verify/runtime/RESULT.md and the toolchain-drift notes.
set(_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_toolchain_prelude.h")

# Per-file: files that need an extra include / warning demotion. Force-includes
# are NEVER applied to posix_strerror_r.cpp (it #undef's _GNU_SOURCE first).
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libbase/hex.cpp
    ${MDVM_NATIVE_SRC_ROOT_DIR}/libprocinfo/process.cpp
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/metrics/metrics_common.cc
    PROPERTIES COMPILE_OPTIONS "-include;${_PRELUDE}")
set_source_files_properties(
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/file_utils.cc
    ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/utils.cc
    PROPERTIES COMPILE_OPTIONS "-Wno-strict-primary-template-shadow")
file(GLOB _DEX_CC ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libdexfile/dex/*.cc)
set_source_files_properties(${_DEX_CC}
    PROPERTIES COMPILE_OPTIONS "-include;${_PRELUDE};-Wno-strict-primary-template-shadow")

# Per-target prelude + shadow demotion, applied to EVERY generated target,
# scoped to C/CXX so .S assembly sources are not fed C headers via -include.
# (The bumped art+libcore at android-16.0.0_r4 need <optional>/<cstring>/<ctime>/... that
# clang-21 libc++ no longer pulls in transitively; the prelude provides them.)
# strlcpy: glibc 2.38 declares it -> ART's host shim self-skips on ANDROID_HOST_MUSL.
get_property(_all_targets DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" PROPERTY BUILDSYSTEM_TARGETS)
foreach(_t IN LISTS _all_targets)
    get_target_property(_ttype ${_t} TYPE)
    # Skip `base` (libbase): it has its own per-file shims above, and a blanket
    # -include would pull <features.h> into posix_strerror_r.cpp BEFORE its
    # deliberate `#undef _GNU_SOURCE`, breaking its POSIX strerror_r selection.
    if(NOT _ttype STREQUAL "INTERFACE_LIBRARY" AND NOT _t STREQUAL "base")
        target_compile_options(${_t} PRIVATE
            "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>"
            "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>"
            # The 2023 sources promote some warnings to errors that clang-21 /
            # glibc-2.34+ now emit. Demote warning-as-error tree-wide. (Cases
            # where an in-source `#pragma clang diagnostic error` re-arms past
            # this -- e.g. thread.cc's -Wconversion on PTHREAD_STACK_MIN -- are
            # handled by vendor source patches instead.) Harness-only.
            "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error>")
        # Project-owned compat shim headers (//compat). Provides android-base/
        # stringify.h, which android-16.0.0_r4 art's macros.h now includes but
        # the archive-pinned 2023 libbase does not ship. Lowest priority (after
        # the real libbase include dirs) so it only fills genuine gaps.
        target_include_directories(${_t} PRIVATE "${MDVM_COMPAT_INCLUDE_DIR}")
        # aconfig-generated feature-flag headers (com_android_art_flags.h,
        # com_android_art_rw_flags.h), staged by the codegen driver. android-16+
        # art includes these across runtime/ + compiler/; on Android they come
        # from the `aconfig` tool, which we reproduce in bp2cmake.aconfig.
        target_include_directories(${_t} PRIVATE "${MDVM_GENSRC_DIR}/art/aconfig/include")
        # A16 libnativehelper header-only headers (utils.h, updated ScopedUtfChars)
        # FIRST, so art compiles against the API it expects rather than the
        # archive's 2023 nativehelper headers (which lack them).
        target_include_directories(${_t} BEFORE PRIVATE "${MDVM_NATIVEHELPER_HDRS_DIR}")
    endif()
endforeach()
foreach(_t art dalvikvm)
    if(TARGET ${_t})
        target_compile_definitions(${_t} PRIVATE ANDROID_HOST_MUSL)
    endif()
endforeach()

# javacorenatives drift shim: libopenjdk's StrictMath.c does
# #include "../../external/fdlibm/fdlibm.h", a relative path that doesn't resolve
# in this layout. Provide an anchor include dir under //compat where it lands on
# the real fdlibm. Same project-owned-glue pattern as the gtest_prod shim.
if(TARGET openjdk)
    target_include_directories(openjdk PRIVATE
        "${_repo}/compat/openjdk_inc/anchor1/anchor2")
endif()
