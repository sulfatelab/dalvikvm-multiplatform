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

# --- Code generation (replaces historical Gradle tasks) --------------------
# operator_out is emitted as add_custom_commands inside the generated file; the
# aconfig headers + two-stage asm_defines + mterp are run here at configure time.
# art/* inputs come from nested vendor/art (--art-root).
file(GLOB _mdvm_mterp_inputs
    "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/mterp/${ART_TARGET_AOSP_ARCH}ng/*.S")
file(GLOB _mdvm_asm_define_inputs
    "${MDVM_ART_ROOT_DIR}/art/tools/cpp-define-generator/*.def")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${_mdvm_mterp_inputs}
    ${_mdvm_asm_define_inputs}
    "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/mterp/gen_mterp.py"
    "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/mterp/common/gen_setup.py"
    "${MDVM_ART_ROOT_DIR}/art/tools/cpp-define-generator/asm_defines.cc"
    "${MDVM_ART_ROOT_DIR}/art/tools/cpp-define-generator/make_header.py"
    "${MDVM_BP2CMAKE}/bp2cmake/codegen.py"
    "${MDVM_BP2CMAKE}/bp2cmake/codegen_main.py")
set(_art_codegen_options)
if(ART_TARGET_PLATFORM STREQUAL "windows")
    list(APPEND _art_codegen_options --os windows)
    execute_process(
        COMMAND ${CMAKE_CXX_COMPILER} -print-resource-dir
        OUTPUT_VARIABLE _art_clang_resource_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _art_resource_rc)
    if(NOT _art_resource_rc EQUAL 0)
        message(FATAL_ERROR "cannot query the selected Clang resource directory")
    endif()
    # Native Windows Clang prints a backslash path.  This value is later used
    # inside a CMake ``SHELL:-isystem`` option, where an unnormalized ``\m``
    # sequence would lose its separators before reaching the GNU-style driver.
    file(TO_CMAKE_PATH "${_art_clang_resource_dir}" _art_clang_resource_dir)
    foreach(_art_codegen_include
            "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/include/c++/v1"
            "${_art_clang_resource_dir}/include"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/ucrt"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/shared"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/um"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/include")
        if(EXISTS "${_art_codegen_include}")
            list(APPEND _art_codegen_options --target-include "${_art_codegen_include}")
        endif()
    endforeach()
endif()
if(ART_TEST_VARIANT STREQUAL "win32-stack-high-water")
    list(APPEND _art_codegen_options --asm-define ART_WIN32_STACK_HIGH_WATER=1)
endif()
set(_art_codegen_kinds aconfig mterp asm_defines)
if(ART_TARGET_PLATFORM STREQUAL "windows")
    list(APPEND _art_codegen_kinds windows_pe_headers)
endif()
foreach(_kind IN LISTS _art_codegen_kinds)
    execute_process(
        COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${MDVM_BP2CMAKE}"
                ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
                --root ${MDVM_NATIVE_SRC_ROOT_DIR} --art-root ${MDVM_ART_ROOT_DIR}
                --libcore-root ${MDVM_LIBCORE_DIR}
                --gensrc ${MDVM_GENSRC_DIR}
                --arch ${ART_TARGET_AOSP_ARCH} --clang ${CMAKE_CXX_COMPILER}
                ${_art_codegen_options} --only ${_kind}
        RESULT_VARIABLE _rc)
    if(NOT _rc EQUAL 0)
        message(FATAL_ERROR "codegen '${_kind}' failed (${_rc})")
    endif()
endforeach()

# --- Platform imported libraries ---------------------------------------------
# These replace AOSP in-tree host libraries. Windows searches only the explicit
# target bundle, never the build host's default library paths.
if(ART_TARGET_PLATFORM STREQUAL "windows")
    function(_art_import_windows_library target)
        set(options)
        set(one_value_args)
        set(multi_value_args NAMES INCLUDE_DIRS LIB_DIRS)
        cmake_parse_arguments(IMPORT "${options}" "${one_value_args}" "${multi_value_args}" ${ARGN})
        find_library(_art_${target}_path NAMES ${IMPORT_NAMES}
            PATHS ${IMPORT_LIB_DIRS} NO_DEFAULT_PATH REQUIRED)
        add_library(${target} UNKNOWN IMPORTED GLOBAL)
        set_target_properties(${target} PROPERTIES IMPORTED_LOCATION "${_art_${target}_path}")
        set(_art_import_includes)
        foreach(_art_import_include IN LISTS IMPORT_INCLUDE_DIRS)
            if(EXISTS "${_art_import_include}")
                list(APPEND _art_import_includes "${_art_import_include}")
            endif()
        endforeach()
        if(_art_import_includes)
            set_target_properties(${target} PROPERTIES
                INTERFACE_INCLUDE_DIRECTORIES "${_art_import_includes}")
        endif()
    endfunction()
    set(_art_bundle_lib "${ART_TARGET_BUNDLE_ROOT}/lib")
    _art_import_windows_library(z
        NAMES z zlib zlibstatic
        INCLUDE_DIRS "${_art_bundle_lib}/zlib/include" "${ART_TARGET_BUNDLE_ROOT}/include"
        LIB_DIRS "${_art_bundle_lib}/zlib/lib" "${_art_bundle_lib}/zlib" "${_art_bundle_lib}")
    _art_import_windows_library(lz4
        NAMES lz4 liblz4
        INCLUDE_DIRS "${_art_bundle_lib}/lz4/include" "${ART_TARGET_BUNDLE_ROOT}/include"
        LIB_DIRS "${_art_bundle_lib}/lz4/lib" "${_art_bundle_lib}/lz4" "${_art_bundle_lib}")
    foreach(_art_lz4_header lz4.h lz4hc.h)
        if(NOT EXISTS "${_art_bundle_lib}/lz4/include/${_art_lz4_header}")
            message(FATAL_ERROR
                "Windows target bundle is missing the LZ4 public header: "
                "${_art_bundle_lib}/lz4/include/${_art_lz4_header}")
        endif()
    endforeach()
    _art_import_windows_library(onecore
        NAMES onecore OneCore
        INCLUDE_DIRS "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/um"
        LIB_DIRS "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/um/${ART_TARGET_AOSP_ARCH}")

    # The Windows profile is deliberately self-contained.  Clang's Windows
    # driver otherwise discovers an MSVC-style C++ include tree and host
    # libraries before the bundle, which makes the same command behave
    # differently on Linux and Windows build hosts.  Keep the C++ and C
    # system include order identical to the checked-in Win64 toolchain.
    set(_art_windows_cxx_include
        "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/include/c++/v1")
    if(NOT EXISTS "${_art_windows_cxx_include}")
        message(FATAL_ERROR
            "Windows target bundle is missing libc++ headers: ${_art_windows_cxx_include}")
    endif()
    set(_art_windows_system_includes
        "${_art_clang_resource_dir}/include"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/ucrt"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/shared"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/um"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/include")
    foreach(_art_windows_system_include IN LISTS _art_windows_system_includes)
        if(NOT EXISTS "${_art_windows_system_include}")
            message(FATAL_ERROR
                "Windows target bundle is missing system headers: ${_art_windows_system_include}")
        endif()
    endforeach()
    # These are INTERFACE link inputs rather than a compiler-global setting so
    # every generated DLL/executable gets the same target CRT contract,
    # including the shared art-compiler product.
    add_library(art_windows_cxx INTERFACE)
    set(_art_windows_cxx_lib "${_art_bundle_lib}/libcxx/lib/c++.lib")
    if(NOT EXISTS "${_art_windows_cxx_lib}")
        message(FATAL_ERROR "Windows target bundle is missing libc++ import library: ${_art_windows_cxx_lib}")
    endif()
    set(_art_windows_cxx_runtime_dll
        "${_art_bundle_lib}/libcxx/bin/c++.dll")
    if(NOT EXISTS "${_art_windows_cxx_runtime_dll}")
        message(FATAL_ERROR
            "Windows target bundle is missing libc++ runtime: "
            "${_art_windows_cxx_runtime_dll}")
    endif()
    target_link_libraries(art_windows_cxx INTERFACE "${_art_windows_cxx_lib}")
    foreach(_art_windows_runtime_lib
            "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/lib/${ART_TARGET_AOSP_ARCH}/msvcprt.lib"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/lib/${ART_TARGET_AOSP_ARCH}/msvcrt.lib"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/lib/${ART_TARGET_AOSP_ARCH}/vcruntime.lib"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/ucrt/${ART_TARGET_AOSP_ARCH}/ucrt.lib"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/um/${ART_TARGET_AOSP_ARCH}/kernel32.lib")
        if(EXISTS "${_art_windows_runtime_lib}")
            target_link_libraries(art_windows_cxx INTERFACE "${_art_windows_runtime_lib}")
        endif()
    endforeach()

    # compiler-rt is versioned below the bundle's lib/clang directory.  Add
    # every regular version directory so a target bundle can be upgraded
    # without changing the maintained CMake entry point.
    file(GLOB _art_windows_compiler_rt_dirs LIST_DIRECTORIES true
        "${ART_TARGET_BUNDLE_ROOT}/lib/clang/*/lib/windows")
    foreach(_art_windows_compiler_rt_dir IN LISTS _art_windows_compiler_rt_dirs)
        if(IS_DIRECTORY "${_art_windows_compiler_rt_dir}")
            target_link_directories(art_windows_cxx INTERFACE
                "${_art_windows_compiler_rt_dir}")
        endif()
    endforeach()
    # Windows uses the pinned expat sources from the repository. This keeps
    # javacore independent of whatever XML library happens to be installed on
    # the build host or omitted from a target SDK bundle.
    add_library(expat STATIC
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/expat/lib/xmlparse.c"
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/expat/lib/xmlrole.c"
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/expat/lib/xmltok.c"
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/expat/lib/xmltok_impl.c"
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/expat/lib/xmltok_ns.c")
    target_include_directories(expat PUBLIC "${MDVM_NATIVE_SRC_ROOT_DIR}/external/expat/lib")
    target_compile_definitions(expat
        PUBLIC XML_STATIC
        PRIVATE HAVE_EXPAT_CONFIG_H XML_DEV_URANDOM)
    add_library(cap INTERFACE)
else()
    find_package(ZLIB REQUIRED)
    add_library(z INTERFACE)
    target_link_libraries(z INTERFACE ZLIB::ZLIB)
    foreach(_hostlib cap lz4)
        find_library(_${_hostlib}_path NAMES ${_hostlib} REQUIRED)
        add_library(${_hostlib} INTERFACE)
        set_target_properties(${_hostlib} PROPERTIES
            INTERFACE_LINK_LIBRARIES "${_${_hostlib}_path}")
    endforeach()
    find_library(_expat_path NAMES expat expatw REQUIRED)
    add_library(expat INTERFACE)
    set_target_properties(expat PROPERTIES INTERFACE_LINK_LIBRARIES "${_expat_path}")
endif()

# Windows' sigchain module is intentionally supplied by the platform source
# tree rather than the portable Blueprint closure. Define it before loading the
# graph so target_link_libraries resolves it as a CMake target, not `-lsigchain`.
if(ART_TARGET_PLATFORM STREQUAL "windows" AND NOT TARGET sigchain)
    set(_art_windows_runtime "${MDVM_ART_ROOT_DIR}/art/runtime/multiplatform/windows")
    add_library(sigchain SHARED "${_art_windows_runtime}/sigchain_windows.cc")
    target_include_directories(sigchain PUBLIC
        "${MDVM_ART_ROOT_DIR}/art"
        "${MDVM_ART_ROOT_DIR}/art/sigchainlib"
        "${MDVM_COMPAT_INCLUDE_DIR}")
    target_compile_definitions(sigchain PRIVATE
        _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI CHAR_BIT=8)
    set_target_properties(sigchain PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
endif()

if(ART_TARGET_PLATFORM STREQUAL "windows" AND NOT TARGET windows_x64_posix_stubs)
    # The common libbase/libprocinfo sources intentionally retain their POSIX
    # API surface.  This regular source library provides the Windows ABI
    # implementation once for the product graph and for the unified probes.
    add_library(windows_x64_posix_stubs STATIC
        "${_repo}/compat/src/windows_x64_posix_stubs.c")
    target_include_directories(windows_x64_posix_stubs PRIVATE
        "${MDVM_COMPAT_INCLUDE_DIR}")
    target_compile_definitions(windows_x64_posix_stubs PRIVATE
        _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI)
    set_target_properties(windows_x64_posix_stubs PROPERTIES
        POSITION_INDEPENDENT_CODE ON)
endif()

# --- The generated graph (target closure, deps-first) -----------------------
include("${ART_GRAPH_FILE}")

if(TARGET art-compiler)
    get_target_property(_art_compiler_type art-compiler TYPE)
    if(NOT _art_compiler_type STREQUAL "SHARED_LIBRARY")
        message(FATAL_ERROR "ART requires art-compiler to be a SHARED target")
    endif()
else()
    message(FATAL_ERROR "Generated ART graph must define the shared art-compiler target")
endif()

if(ART_TARGET_PLATFORM STREQUAL "windows")
    # The graph deliberately contains only portable ART sources. These are the
    # target-OS implementations that used to be injected by phase1.cmake.
    set(_art_windows_runtime "${MDVM_ART_ROOT_DIR}/art/runtime/multiplatform/windows")
    set(_art_windows_openjdk "${MDVM_ART_ROOT_DIR}/art/openjdkjvm")
    if(TARGET procinfo)
        # libprocinfo is Linux /proc-only. Keep its logical target so the
        # common unwindstack graph remains identical, but compile a deliberate
        # empty Windows DSO because the header exposes no Windows API.
        target_sources(procinfo PRIVATE "${_repo}/compat/src/windows_procinfo_stub.cc")
    endif()
    if(TARGET dexfile)
        # The Windows runtime uses the same ART dex API bridge as the former
        # phase build; keep those ADexFile_* definitions in the common graph.
        target_sources(dexfile PRIVATE
            "${MDVM_ART_ROOT_DIR}/art/libdexfile/external/dex_file_ext.cc"
            "${MDVM_ART_ROOT_DIR}/art/libdexfile/external/dex_file_supp.cc")
    endif()
    if(TARGET unwindstack)
        # The portable graph names the Linux GAS helper. Windows uses the
        # regular C ABI stub from ART's platform tree instead.
        target_sources(unwindstack PRIVATE
            "${MDVM_ART_ROOT_DIR}/art/multiplatform/windows/AsmGetRegs_stub.c")
    endif()
    foreach(_art_cpu_target cpu_features art dex2oat_static)
        if(TARGET ${_art_cpu_target})
            target_sources(${_art_cpu_target} PRIVATE
                "${MDVM_ART_ROOT_DIR}/external/cpu_features/src/impl_x86_windows.c")
        endif()
    endforeach()
    if(TARGET artbase)
        # VirtualAlloc2 and MapViewOfFile3 are imported from the Windows 10
        # OneCore SDK library, not from the build host's default libraries.
        target_link_libraries(artbase onecore)
    endif()
    if(TARGET art)
        target_sources(art PRIVATE
            "${_art_windows_runtime}/thread_windows.cc"
            "${_art_windows_runtime}/stack_windows.cc"
            "${_art_windows_runtime}/cet_compat.cc"
            "${_art_windows_runtime}/jit_unwind_windows.cc"
            "${_art_windows_runtime}/runtime_windows.cc"
            "${_art_windows_runtime}/monitor_windows.cc"
            "${_art_windows_openjdk}/openjdkjvm_memory_windows.cc")

        # CMake's Clang ASM rule declares a depfile without asking Clang to
        # populate it.  Record the shared support inputs explicitly so a
        # header/assembly edit cannot leave stale x86_64 runtime objects in an
        # otherwise incremental Ninja build.
        set(_art_x86_64_asm_support_deps
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/asm_support_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/asm_support_x86_64.h"
            "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/cfi_asm_support.h"
            "${MDVM_ART_ROOT_DIR}/art/runtime/asm_support.h")
        set_property(SOURCE
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/memcmp16_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/native_entrypoints_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/jni_entrypoints_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/quick_entrypoints_x86_64.S"
            "${MDVM_GENSRC_DIR}/art/asm/mterp/mterp_x86_64.S"
            APPEND PROPERTY OBJECT_DEPENDS "${_art_x86_64_asm_support_deps}")
    endif()
    if(TARGET openjdkjvm)
        # Keep socket-fd ownership process-wide. libjavacore, libopenjdk, NIO,
        # and the JVM_* bridge must not each absorb a private registry copy.
        target_sources(openjdkjvm PRIVATE
            "${_repo}/compat/src/windows_x64_socket_posix.c"
            "${_repo}/compat/src/windows_x64_socket_fd_registry.c")
        if(TARGET javacore)
            target_link_libraries(javacore openjdkjvm)
        endif()
    endif()
    if(TARGET javacore)
        # Replace the Linux libcore.io backend with the existing Windows JNI
        # bridge while retaining the common Memory/NetworkUtilities sources.
        target_sources(javacore PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/register_libcore_io_Linux_win.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/AsynchronousCloseMonitor_win.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/android_system_OsConstantsHolder_win.cpp"
            "${_repo}/tools/windows_x64/jni_stubs/win_path.c"
            "${_repo}/tools/windows_x64/jni_stubs/win_fs_natives.c"
            "${_repo}/tools/windows_x64/jni_stubs/win_net_natives.c"
            "${_repo}/tools/windows_x64/jni_stubs/libcore_hello3.c")
        target_include_directories(javacore BEFORE PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native"
            "${MDVM_LIBCORE_DIR}/luni/src/main/native"
            "${_repo}/tools/windows_x64/jni_stubs")
        target_compile_definitions(javacore PRIVATE MDVM_SOCKET_FD_TRACKING=1)
        target_link_libraries(javacore openjdkjvm icuuc icui18n)
    endif()
    if(TARGET openjdk)
        # Keep the portable Java/native modules and swap only the Unix process,
        # thread, close, OnLoad, and excluded NIO.2 registration surfaces.
        target_sources(openjdk PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/openjdk_OnLoad_win.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/win_close.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/NativeThread_win.c"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/AsynchronousCloseMonitor_win.cpp"
            "${_repo}/tools/windows_x64/jni_stubs/win_runtime_natives.c"
            "${_repo}/tools/windows_x64/jni_stubs/libcore_hello3.c"
            "${_repo}/tools/windows_x64/jni_stubs/win_process_natives.c"
            "${_repo}/compat/src/openjdk_excluded_registers_windows.cc")
        target_include_directories(openjdk BEFORE PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native"
            "${MDVM_LIBCORE_DIR}/luni/src/main/native"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native"
            "${_repo}/tools/windows_x64/jni_stubs")
        set(_art_windows_openjdk_linuxish_c
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileDispatcherImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/IOUtil.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/Net.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/net_util_md.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/net_util.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/EPoll.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/ServerSocketChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/DatagramChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/DatagramDispatcher.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/PollArrayWrapper.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileKey.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/MappedByteBuffer.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileInputStream.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/io_util_md.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketInputStream.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketOutputStream.c")
        set_source_files_properties(${_art_windows_openjdk_linuxish_c}
            PROPERTIES COMPILE_DEFINITIONS "__linux__=1;MDVM_SOCKET_FD_TRACKING=1")
        target_link_libraries(openjdk openjdkjvm icuuc)
    endif()
    if(TARGET javacore OR TARGET openjdk)
        # The shared legacy fallback source must not provide either product
        # DSO's authoritative JNI_OnLoad entry point.
        set_source_files_properties(
            "${_repo}/tools/windows_x64/jni_stubs/libcore_hello3.c"
            PROPERTIES COMPILE_DEFINITIONS
                "JNI_OnLoad=mdvm_stub_JNI_OnLoad_unused;JNI_OnUnload=mdvm_stub_JNI_OnUnload_unused")
    endif()
    if(TARGET lzma)
        # The portable graph intentionally omits AesOpt.c.  Keep the same
        # scalar AES contract as the former Windows phase rather than probing
        # host CPU features or requiring AES-NI at link time.
        target_sources(lzma PRIVATE
            "${MDVM_ART_ROOT_DIR}/art/multiplatform/windows/lzma_aes_stub.c")
        target_compile_definitions(lzma PRIVATE MY_CPU_X86_OR_AMD64=0)
    endif()
    # Keep the PE product name stable and omit CMake's conventional lib prefix.
    set_target_properties(art-compiler PROPERTIES
        PREFIX ""
        OUTPUT_NAME "art-compiler"
        WINDOWS_EXPORT_ALL_SYMBOLS OFF)
    target_sources(art-compiler PRIVATE "${_repo}/compat/src/art_compiler_exports.cc")
    target_sources(art PRIVATE "${_repo}/compat/src/art_pe_inline_exports.cc")
    target_include_directories(art-compiler PRIVATE "${MDVM_ART_ROOT_DIR}/art/compiler")
    # Select the PE import side of ART's existing LIBART_PE_* boundary.  This
    # also makes Thread::Current() call the exported accessor instead of
    # attempting to import C++ thread_local storage from art.dll.
    target_compile_definitions(art-compiler PRIVATE ART_CONSUMING_LIBART)
    target_link_options(art-compiler PRIVATE
        "LINKER:/DEF:${_repo}/compat/art_compiler_exports.def")
    # fmtlib is compiled as part of several generated libraries.  The Android
    # graph disables exceptions globally, but fmt's format.cc intentionally
    # uses throw; keep this narrowly scoped source override in the unified
    # graph just as the former Windows phase did.
    set_source_files_properties(
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/fmtlib/src/format.cc"
        PROPERTIES COMPILE_OPTIONS "-fexceptions;-UNDEBUG")
endif()

# --- Toolchain-drift shims (2023 sources vs clang-21; harness-level only) ----
# These compensate for source/toolchain drift and disappear when submodules are
# bumped to current AOSP. NONE of this is in the converter or the overlay. See
# bp2cmake_linux_scope.md and the toolchain-drift notes.
if(ART_TARGET_PLATFORM STREQUAL "windows")
    set(_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_windows_x64_prelude.h")
    set(_art_windows_system_compile_options)
    foreach(_art_windows_system_include IN LISTS _art_windows_system_includes)
        list(APPEND _art_windows_system_compile_options
            "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-isystem ${_art_windows_system_include}>")
    endforeach()
else()
    set(_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_toolchain_prelude.h")
    if(TARGET openjdkjvmti)
        # The pinned JVMTI sources assume bionic's global nullptr_t and predate
        # glibc 2.38's strlcpy. Keep that host-toolchain drift isolated to the
        # one DSO instead of changing the nested vendor source.
        target_compile_options(openjdkjvmti PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include ${MDVM_COMPAT_INCLUDE_DIR}/mdvm_openjdkjvmti_linux_prelude.h>")
    endif()
endif()

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
if(ART_TARGET_PLATFORM STREQUAL "windows")
    # Windows headers define CALLBACK as __stdcall, but ICU's ucnvisci.cpp
    # uses CALLBACK as a private goto label. Keep the forced compatibility
    # prelude and suppress that macro for this source only.
    set_property(SOURCE
        ${MDVM_ICU_DIR}/icu4c/source/common/ucnvisci.cpp
        APPEND PROPERTY COMPILE_DEFINITIONS MDVM_WINDOWS_NO_CALLBACK_MACRO)
endif()
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
    if(ART_TEST_VARIANT STREQUAL "win32-frame-attribution" AND
       _t STREQUAL "art")
        target_compile_definitions(${_t} PRIVATE ART_W003_FRAME_PROBE=1)
        # The internal counters are global only so generated nterp assembly can
        # reference their defining quick-entrypoint object. Export only the two
        # functions consumed by the frame probe; product art.dll receives
        # neither this macro nor these linker directives.
        target_link_options(${_t} PRIVATE
            "LINKER:/EXPORT:art_w003_frame_probe_reset"
            "LINKER:/EXPORT:art_w003_frame_probe_snapshot")
    endif()
    if(ART_TEST_VARIANT STREQUAL "win32-stack-high-water" AND
       NOT _ttype STREQUAL "UTILITY" AND
       NOT _ttype STREQUAL "INTERFACE_LIBRARY")
        target_compile_definitions(${_t} PRIVATE ART_WIN32_STACK_HIGH_WATER=1)
    endif()
    # Skip `base` (libbase): it has its own per-file shims above, and a blanket
    # -include would pull <features.h> into posix_strerror_r.cpp BEFORE its
    # deliberate `#undef _GNU_SOURCE`, breaking its POSIX strerror_r selection.
    if(NOT _ttype STREQUAL "INTERFACE_LIBRARY" AND
       (NOT _t STREQUAL "base" OR ART_TARGET_PLATFORM STREQUAL "windows"))
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
        if(ART_TARGET_PLATFORM STREQUAL "windows")
            # The bundle is a regular-file projection of libc++, UCRT, and the
            # Windows SDK. No host include or library search path is allowed.
            target_include_directories(${_t} BEFORE PRIVATE
                "${_art_windows_cxx_include}"
                ${_art_windows_system_includes})
            target_compile_options(${_t} PRIVATE
                # Suppress Clang's implicit MSVC STL search and reproduce the
                # same libc++/resource/UCRT order for every source language.
                "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
                "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-isystem ${_art_windows_cxx_include}>"
                ${_art_windows_system_compile_options}
                "$<$<COMPILE_LANGUAGE:C,CXX>:-stdlib=libc++>"
                "$<$<COMPILE_LANGUAGE:C,CXX>:-fms-compatibility>"
                "$<$<COMPILE_LANGUAGE:C,CXX>:-fms-extensions>"
                "$<$<COMPILE_LANGUAGE:C,CXX>:-fno-omit-frame-pointer>")
            foreach(_art_bundle_lib_dir
                    "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/lib"
                    "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/ucrt/${ART_TARGET_AOSP_ARCH}"
                    "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/um/${ART_TARGET_AOSP_ARCH}"
                    "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/lib/${ART_TARGET_AOSP_ARCH}")
                if(EXISTS "${_art_bundle_lib_dir}")
                    target_link_directories(${_t} BEFORE PRIVATE "${_art_bundle_lib_dir}")
                endif()
            endforeach()
        endif()
    endif()
    if(_ttype STREQUAL "EXECUTABLE" OR _ttype STREQUAL "SHARED_LIBRARY" OR
       _ttype STREQUAL "MODULE_LIBRARY")
        target_link_options(${_t} PRIVATE -fuse-ld=lld)
        if(ART_TARGET_PLATFORM STREQUAL "windows")
            # bp2cmake emits the plain target_link_libraries signature; keep
            # this augmentation in the same signature family.
            target_link_libraries(${_t} art_windows_cxx)
        endif()
    endif()
    if(ART_TARGET_PLATFORM STREQUAL "windows" AND
       NOT _t STREQUAL "windows_x64_posix_stubs" AND
       NOT _ttype STREQUAL "UTILITY" AND
       NOT _ttype STREQUAL "INTERFACE_LIBRARY")
        # Keep the compatibility ABI and its target socket imports available
        # to every generated library/executable and to future stage probes.
        target_link_libraries(${_t} windows_x64_posix_stubs ws2_32 synchronization)
    endif()
    if(ART_TARGET_PLATFORM STREQUAL "windows" AND
       _ttype STREQUAL "SHARED_LIBRARY" AND
       NOT _t STREQUAL "art" AND NOT _t STREQUAL "art-compiler")
        # Windows import libraries are required by downstream generated
        # targets (for example base -> log).  art.dll uses the source-level
        # EXPORT/LIBART_PE_* ABI so Debug-only inline/template COMDAT symbols
        # cannot overflow PE's export table.  The compiler DSO has the
        # reviewed DEF allowlist above.
        set_target_properties(${_t} PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
    endif()
    if(_ttype STREQUAL "EXECUTABLE")
        if(ART_TARGET_PLATFORM STREQUAL "linux")
            target_compile_options(${_t} PRIVATE -fPIE)
            target_link_options(${_t} PRIVATE -pie)
        endif()
    endif()
endforeach()
if(ART_TARGET_PLATFORM STREQUAL "windows")
    # Python stages include-guard-compatible copies of the few ART headers
    # whose cross-DSO data needs explicit dllexport/dllimport on PE. Force the
    # same declarations into art.dll and its dex2oat consumer without touching
    # the nested vendor checkout.
    set(_art_windows_pe_headers
        "${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/base/locks.h"
        "${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/well_known_classes.h"
        "${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/oat/oat_quick_method_header.h")
    foreach(_art_pe_target art art-dex2oat)
        if(TARGET ${_art_pe_target})
            # The generated oat header no longer sits beside stack_map.h, so
            # preserve the original quoted-include lookup explicitly.
            target_include_directories(${_art_pe_target} PRIVATE
                "${MDVM_ART_ROOT_DIR}/art/runtime/oat")
            foreach(_art_pe_header IN LISTS _art_windows_pe_headers)
                target_compile_options(${_art_pe_target} PRIVATE
                    "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include ${_art_pe_header}>")
            endforeach()
        endif()
    endforeach()
    set(_art_windows_runtime_options_header
        "${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/runtime_options.h")
    # Only the defining TU and dex2oat's consuming TU use cross-DSO runtime
    # option keys; keep this overlay source-scoped to avoid broad rebuilds.
    set_property(SOURCE
        "${MDVM_ART_ROOT_DIR}/art/runtime/runtime_options.cc"
        "${MDVM_ART_ROOT_DIR}/art/dex2oat/dex2oat.cc"
        APPEND PROPERTY COMPILE_OPTIONS
            "-include;${_art_windows_runtime_options_header}")

    # The PE product boundary stays source-level and bounded.  Only the two
    # defining translation units see the JVMTI-specific header overlays; the
    # plugin's ordinary function references resolve through art.lib.  The two
    # C dlmalloc entry points are instantiated by inline ART allocation paths
    # in libopenjdkjvmti and therefore need equally explicit exports.
    set_property(SOURCE
        "${MDVM_ART_ROOT_DIR}/art/runtime/thread.cc"
        APPEND PROPERTY COMPILE_OPTIONS
            "-include;${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/thread.h")
    set_property(SOURCE
        "${MDVM_ART_ROOT_DIR}/art/runtime/art_method.cc"
        APPEND PROPERTY COMPILE_OPTIONS
            "-include;${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/art_method.h")
    # W-025 JNI DSOs inspect whether collection is enabled and audit the
    # current JIT mapping. Keep those two function exports source-scoped to
    # the defining translation unit just like the other bounded PE overlays.
    set_property(SOURCE
        "${MDVM_ART_ROOT_DIR}/art/runtime/jit/jit_code_cache.cc"
        APPEND PROPERTY COMPILE_OPTIONS
            "-include;${MDVM_GENSRC_DIR}/art/windows-pe-headers/art/runtime/jit/jit_code_cache.h")
    target_link_options(art PRIVATE
        "LINKER:/EXPORT:mspace_malloc"
        "LINKER:/EXPORT:mspace_usable_size")
endif()
foreach(_t art dalvikvm)
    if(TARGET ${_t} AND ART_TARGET_PLATFORM STREQUAL "linux")
        target_compile_definitions(${_t} PRIVATE ANDROID_HOST_MUSL)
    endif()
endforeach()

# javacorenatives drift shim: libopenjdk's StrictMath.c does
# #include "../../external/fdlibm/fdlibm.h", a relative path that doesn't resolve
# in this layout. Provide an anchor include dir under //compat where it lands on
# the real fdlibm. Same project-owned-glue pattern as the gtest_prod shim.
if(TARGET openjdk)
    target_include_directories(openjdk PRIVATE
        "${_repo}/compat/openjdk_fdlibm/include_root/anchor1/anchor2")
endif()

option(ART_BUILD_TESTS "Define the unified target-aware ART test catalog" ON)
if(ART_BUILD_TESTS)
    include(CTest)
    add_subdirectory("${_repo}/tests" tests)
endif()
