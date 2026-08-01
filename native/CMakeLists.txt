# Top-level native build for the ART product on Linux and Windows.
#
# tools/build_art.py generates one target-resolved graph/profile from nested
# vendor/ Android.bp files and configures this maintained CMake entry point.
# This file contains only project-owned glue that the converter cannot derive:
#   - target SDK/dependency imports;
#   - Python code generation (aconfig, mterp, and asm_defines); and
#   - source/toolchain compatibility policy.
#
# Supported configuration starts with:
#   python tools/build_art.py configure --target-id linux-x86_64-gnu

cmake_minimum_required(VERSION 3.16)

set(ART_PROFILE_FILE "" CACHE FILEPATH "Generated ART target profile")
if(NOT ART_PROFILE_FILE)
    message(FATAL_ERROR
        "ART_PROFILE_FILE is required; configure through tools/build_art.py")
endif()
include("${ART_PROFILE_FILE}")
set(ART_TEST_VARIANT "product" CACHE STRING
    "Build identity: product or an explicit test-only instrumentation variant")
set_property(CACHE ART_TEST_VARIANT PROPERTY STRINGS
    product win32-frame-attribution win32-stack-high-water)
if(NOT ART_TEST_VARIANT MATCHES
   "^(product|win32-frame-attribution|win32-stack-high-water)$")
    message(FATAL_ERROR "Unknown ART_TEST_VARIANT: ${ART_TEST_VARIANT}")
endif()
if((ART_TEST_VARIANT STREQUAL "win32-frame-attribution" OR
    ART_TEST_VARIANT STREQUAL "win32-stack-high-water") AND
   NOT ART_TARGET_ID STREQUAL "windows-x86_64-msvc")
    message(FATAL_ERROR
        "${ART_TEST_VARIANT} is an exact windows-x86_64-msvc test variant")
endif()
if(NOT ART_TARGET_PLATFORM MATCHES "^(linux|windows)$")
    message(FATAL_ERROR
        "The native product entry point admits Linux and Windows targets; "
        "got ${ART_TARGET_ID}.")
endif()
foreach(_art_required_profile_value
        ART_TARGET_ID ART_TARGET_TRIPLE ART_TARGET_PLATFORM ART_TARGET_ARCH
        ART_TARGET_BASE_ISA ART_TARGET_AOSP_ARCH ART_TARGET_ABI
        ART_TARGET_ID_ENUM ART_TARGET_PLATFORM_ENUM ART_TARGET_ARCH_ENUM
        ART_TARGET_ABI_ENUM)
    if(NOT ${_art_required_profile_value})
        message(FATAL_ERROR
            "Target profile omits required ${_art_required_profile_value}")
    endif()
endforeach()
if(ART_TARGET_TRIPLE AND NOT CMAKE_ASM_COMPILER_TARGET)
    set(CMAKE_ASM_COMPILER_TARGET "${ART_TARGET_TRIPLE}" CACHE STRING
        "Target triple for Clang's GNU-style ASM driver")
endif()

project(MinDalvikVM CXX C ASM)

if(NOT CMAKE_GENERATOR STREQUAL "Ninja")
    message(FATAL_ERROR "ART requires the single-config Ninja generator")
endif()
if(NOT CMAKE_C_COMPILER_ID STREQUAL "Clang" OR
   NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang" OR
   NOT CMAKE_ASM_COMPILER_ID STREQUAL "Clang")
    message(FATAL_ERROR
        "ART requires LLVM Clang for C, C++, and ASM (got "
        "${CMAKE_C_COMPILER_ID}/${CMAKE_CXX_COMPILER_ID}/${CMAKE_ASM_COMPILER_ID})")
endif()
if(NOT CMAKE_C_COMPILER_FRONTEND_VARIANT STREQUAL "GNU" OR
   NOT CMAKE_CXX_COMPILER_FRONTEND_VARIANT STREQUAL "GNU")
    message(FATAL_ERROR "ART requires Clang's GNU-style driver frontend")
endif()
if(ART_TARGET_ABI STREQUAL "msvc" AND
   NOT CMAKE_MSVC_RUNTIME_LIBRARY STREQUAL "MultiThreadedDLL")
    message(FATAL_ERROR
        "MSVC-ABI targets require the release dynamic CRT in every build type; "
        "configure through tools/build_art.py")
endif()
get_filename_component(_art_c_compiler_name "${CMAKE_C_COMPILER}" NAME)
get_filename_component(_art_cxx_compiler_name "${CMAKE_CXX_COMPILER}" NAME)
if(_art_c_compiler_name MATCHES "^(clang-cl|clang-mingw|gcc|cc)(\\.exe)?$" OR
   _art_cxx_compiler_name MATCHES "^(clang-cl|clang-mingw|g\\+\\+|cl)(\\.exe)?$")
    message(FATAL_ERROR "ART requires the plain Clang GNU-style driver")
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
set(ART_GRAPH_FILE "" CACHE FILEPATH "Target-resolved bp2cmake graph")
if(NOT ART_GRAPH_FILE)
    message(FATAL_ERROR
        "ART_GRAPH_FILE is required; generate through tools/build_art.py")
endif()
set(ART_LLVM_READOBJ "" CACHE FILEPATH "Configured host llvm-readobj executable")
set(ART_LLVM_OBJDUMP "" CACHE FILEPATH "Configured host llvm-objdump executable")
foreach(_art_llvm_tool ART_LLVM_READOBJ ART_LLVM_OBJDUMP)
    if(NOT ${_art_llvm_tool})
        message(FATAL_ERROR
            "${_art_llvm_tool} is required; configure through tools/build_art.py")
    endif()
endforeach()
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
set(ART_TARGET_BUNDLE_ROOT "" CACHE PATH
    "Regular-file target SDK/dependency bundle (required for Windows targets)")
set(ART_TARGET_SDK_ROOT "" CACHE PATH "Target SDK root")
set(ART_TARGET_SYSROOT "" CACHE PATH "Target sysroot")
set(ART_TARGET_RUNTIME_ROOT "" CACHE PATH "Target runtime root")

if(ART_TARGET_PLATFORM STREQUAL "windows")
    if(NOT ART_TARGET_BUNDLE_ROOT)
        message(FATAL_ERROR
            "Windows targets require ART_TARGET_BUNDLE_ROOT; host libraries are forbidden")
    endif()
    if(NOT EXISTS "${ART_TARGET_BUNDLE_ROOT}")
        message(FATAL_ERROR "Windows target bundle does not exist: ${ART_TARGET_BUNDLE_ROOT}")
    endif()
endif()

include("${CMAKE_CURRENT_LIST_DIR}/cmake/ArtCodegen.cmake")

# Platform SDK/import targets and the two handwritten Windows compatibility
# targets are common entry-point policy, not separate target build graphs.
include("${CMAKE_CURRENT_LIST_DIR}/cmake/ArtPlatform.cmake")

include("${CMAKE_CURRENT_LIST_DIR}/cmake/ArtTargetGraph.cmake")

include("${CMAKE_CURRENT_LIST_DIR}/cmake/ArtCompatibility.cmake")

option(ART_BUILD_TESTS "Define the unified target-aware ART test catalog" ON)
if(ART_BUILD_TESTS)
    include(CTest)
    add_subdirectory("${_repo}/tests" tests)
endif()
