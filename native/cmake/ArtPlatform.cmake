# Platform SDK/import targets for the common ART product entry point.
# Windows searches only the explicit regular-file target bundle; Linux resolves
# the reviewed host library set. This file must not become a target entry point.

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

    file(GLOB _art_windows_compiler_rt_dirs LIST_DIRECTORIES true
        "${ART_TARGET_BUNDLE_ROOT}/lib/clang/*/lib/windows")
    foreach(_art_windows_compiler_rt_dir IN LISTS _art_windows_compiler_rt_dirs)
        if(IS_DIRECTORY "${_art_windows_compiler_rt_dir}")
            target_link_directories(art_windows_cxx INTERFACE
                "${_art_windows_compiler_rt_dir}")
        endif()
    endforeach()
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
    function(_art_import_linux_system_library target link_name)
        find_library(_art_${target}_path NAMES ${ARGN} REQUIRED)
        add_library(${target} INTERFACE)
        if(ART_TARGET_SYSROOT)
            # The discovered regular file proves that the declared target
            # sysroot provides this dependency. Link it by its canonical
            # system name so CMake does not encode the sysroot's /lib as an
            # absolute product RUNPATH.
            target_link_libraries(${target} INTERFACE "-l${link_name}")
        else()
            set_target_properties(${target} PROPERTIES
                INTERFACE_LINK_LIBRARIES "${_art_${target}_path}")
        endif()
    endfunction()
    _art_import_linux_system_library(z z z)
    _art_import_linux_system_library(cap cap cap)
    _art_import_linux_system_library(lz4 lz4 lz4)
    _art_import_linux_system_library(expat expat expat expatw)
endif()

# Windows supplies sigchain from its platform source tree before the generated
# graph is loaded, so downstream references resolve to this CMake target.
if(ART_TARGET_PLATFORM STREQUAL "windows" AND NOT TARGET sigchain)
    set(_art_windows_runtime "${MDVM_ART_ROOT_DIR}/art/runtime/multiplatform/windows")
    add_library(sigchain SHARED "${_art_windows_runtime}/sigchain_windows.cc")
    target_include_directories(sigchain PUBLIC
        "${MDVM_ART_ROOT_DIR}/art"
        "${MDVM_ART_ROOT_DIR}/art/sigchainlib"
        "${MDVM_COMPAT_INCLUDE_DIR}")
    target_compile_definitions(sigchain PRIVATE
        _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI CHAR_BIT=8)
    target_link_options(sigchain PRIVATE
        "LINKER:/CETCOMPAT:NO"
        "LINKER:/DYNAMICBASE"
        "LINKER:/NXCOMPAT"
        "LINKER:/HIGHENTROPYVA")
    set_target_properties(sigchain PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
endif()

if(ART_TARGET_PLATFORM STREQUAL "windows" AND NOT TARGET windows_x64_posix_stubs)
    add_library(windows_x64_posix_stubs STATIC
        "${_repo}/compat/src/windows_x64_posix_stubs.c")
    target_include_directories(windows_x64_posix_stubs PRIVATE
        "${MDVM_COMPAT_INCLUDE_DIR}")
    target_compile_definitions(windows_x64_posix_stubs PRIVATE
        _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI)
    set_target_properties(windows_x64_posix_stubs PROPERTIES
        POSITION_INDEPENDENT_CODE ON)
endif()
