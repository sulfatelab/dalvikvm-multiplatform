# Apply source/toolchain drift shims and common target-level compile/link
# policy after the generated graph is loaded. This common include is not an
# entry point.

# --- Toolchain-drift shims (2023 sources vs clang-21; harness-level only) ----
# These compensate for source/toolchain drift and disappear when submodules are
# bumped to current AOSP. NONE of this is in the converter or the overlay. See
# bp2cmake_linux_scope.md and the toolchain-drift notes.
if(ART_TARGET_PLATFORM STREQUAL "windows")
    set(_PRELUDE "${MDVM_COMPAT_INCLUDE_DIR}/mdvm_windows_x64_prelude.h")
    # These dependencies either own their Windows portability or have an
    # explicit source split below. Keep the list explicit so a newly generated
    # target cannot silently become prelude-free.
    set(_art_windows_prelude_free_targets
        androidio
        art-dex2oat
        art-disassembler
        artpalette
        crypto_static
        dalvikvm
        dex2oat
        elffile
        expat
        fdlibm
        icui18n
        icu
        icuuc
        icuuc_stubdata
        log
        lzma
        nativebridge
        nativehelper
        nativeloader
        odrstatslog
        openjdkjvm
        profile
        procinfo
        sigchain
        unwindstack
        windows_x64_posix_stubs
        ziparchive)
    set(_art_windows_prelude_free_definitions
        _CRT_SECURE_NO_WARNINGS
        NOMINMAX
        WIN32_LEAN_AND_MEAN
        NOGDI)
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
if(ART_TARGET_PLATFORM STREQUAL "linux")
    set_property(SOURCE
        ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/file_utils.cc
        APPEND PROPERTY COMPILE_OPTIONS "-include;filesystem")
    set_property(SOURCE
        ${MDVM_NATIVE_SRC_ROOT_DIR}/art/libartbase/base/time_utils.cc
        APPEND PROPERTY COMPILE_OPTIONS "-include;limits")
    set_property(SOURCE
        ${MDVM_NATIVE_SRC_ROOT_DIR}/art/runtime/runtime_common.cc
        APPEND PROPERTY COMPILE_OPTIONS "-include;signal.h")
endif()
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
if(ART_TARGET_PLATFORM STREQUAL "linux")
    set_property(SOURCE
        ${MDVM_GENSRC_DIR}/art/libdexfile/dex/invoke_type.h.operator_out.cc
        APPEND PROPERTY COMPILE_OPTIONS "-include;stdint.h")
endif()
if(ART_TARGET_PLATFORM STREQUAL "windows")
    # art-dex2oat embeds BoringSSL's crypto sources directly. BoringSSL owns
    # its Windows portability; only ART's 19 dex2oat sources and one generated
    # operator-out source consume the ART compatibility prelude.
    get_target_property(_art_dex2oat_sources art-dex2oat SOURCES)
    set(_art_dex2oat_compat_sources)
    foreach(_art_dex2oat_source IN LISTS _art_dex2oat_sources)
        if(NOT _art_dex2oat_source MATCHES "/external/boringssl/")
            list(APPEND _art_dex2oat_compat_sources "${_art_dex2oat_source}")
        endif()
    endforeach()
    list(LENGTH _art_dex2oat_compat_sources _art_dex2oat_compat_source_count)
    if(NOT _art_dex2oat_compat_source_count EQUAL 20)
        message(FATAL_ERROR
            "Review art-dex2oat Windows prelude scope: expected 20 ART sources, "
            "got ${_art_dex2oat_compat_source_count}")
    endif()
    set_property(SOURCE ${_art_dex2oat_compat_sources}
        APPEND PROPERTY COMPILE_OPTIONS "-include;${_PRELUDE}")

    # libziparchive includes the Windows CRT stdio surface directly. Keep its
    # 64-bit POSIX spellings on the dependency target instead of inheriting
    # them from ART's forced compatibility prelude.
    target_compile_definitions(ziparchive PRIVATE
        fseeko=_fseeki64
        fseeko64=_fseeki64
        ftello=_ftelli64
        ftello64=_ftelli64)
endif()

# Common generated-target policy. Windows receives its platform compatibility
# prelude for C/CXX only, so .S assembly sources are not fed C headers via
# -include. Linux toolchain drift stays source- or module-scoped above.
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
        if(ART_TARGET_PLATFORM STREQUAL "windows" AND
           _t IN_LIST _art_windows_prelude_free_targets)
            target_compile_definitions(${_t} PRIVATE
                ${_art_windows_prelude_free_definitions})
        endif()
        # The Windows compatibility header supplies target-platform APIs and
        # declarations to every generated PE target. Linux toolchain drift is
        # kept in the explicit source/module shims above instead of forcing a
        # standard-header prelude into the complete product graph.
        if(ART_TARGET_PLATFORM STREQUAL "windows" AND
           NOT _t IN_LIST _art_windows_prelude_free_targets)
            target_compile_options(${_t} PRIVATE
                "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")
        endif()
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
    # Clang's quoted-include fallback for a forced generated header differs
    # between Windows and Linux hosts.  Keep the projected jit_code_cache.h
    # explicitly anchored to its unchanged source siblings on both hosts.
    set_property(SOURCE
        "${MDVM_ART_ROOT_DIR}/art/runtime/runtime_options.cc"
        "${MDVM_ART_ROOT_DIR}/art/dex2oat/dex2oat.cc"
        "${MDVM_ART_ROOT_DIR}/art/runtime/jit/jit_code_cache.cc"
        APPEND PROPERTY INCLUDE_DIRECTORIES
            "${MDVM_ART_ROOT_DIR}/art/runtime/jit")

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
